"""校对引擎 — 严格 zcheck 风格。

主流程(POST /documents/{id}/proofread)由 skill_registry.run_pipeline 调度,
当前 skill 顺序(按 phase):
  20: builtin.l1_l3_fast_pass    — L1+L2+L3 合并一次 LLM(FAST_SYSTEM)
  30: builtin.l4_consistency     — L4 三步法(候选+复核)

L5 不在主流程,在用户 ✓ 接受 时触发(routes 层):
  - Python 快检(秒级,5 类风险)
  - 如 USE_LLM + ENABLE_L5_AI → 后台异步 LLM 复核

导出前再跑一次 L5 快检阻断。
"""
from __future__ import annotations
import asyncio
import re
import uuid
from collections import defaultdict
from typing import Any, Callable

from ..core import config
from ..schemas import Confidence, ErrorMetadata, FindingSource, Layer, Paragraph, ProofreadError, ReviewStatus
from . import llm, prompts
from .chunker import Chunker


# ============================================================================
# 主入口
# ============================================================================
async def aproofread(
    doc_id: str,
    paragraphs: list[Paragraph],
    rules: list[Any] | None = None,
    on_progress: Callable[[str, int, int, list], None] | None = None,
) -> list[ProofreadError]:
    """跑主校对流水线 — 现在走 skill registry 调度(可插拔)。"""
    from ..schemas import SkillContext
    from . import skill_registry

    ctx = SkillContext(
        doc_id=doc_id, paragraphs=paragraphs,
        user_rules=rules or [], on_progress=on_progress,
    )
    all_errors = await skill_registry.run_pipeline(ctx)

    # 应用用户规则过滤 + 去重
    if rules:
        all_errors = _filter_by_rules(all_errors, rules)
    return _aggregate(all_errors)


def proofread(*args, **kw) -> list[ProofreadError]:
    return asyncio.run(aproofread(*args, **kw))


# ============================================================================
# Phase 2: Fast LLM Pass(zcheck 风格)
# ============================================================================
async def _run_fast_pass(
    doc_id: str, paragraphs: list[Paragraph], rules: list[Any],
    on_progress: Callable | None = None,
) -> list[ProofreadError]:
    chunker = Chunker(target_chars=config.LLM_CHUNK_CHARS, context_chars=200)
    chunks = chunker.split(paragraphs)
    semaphore = asyncio.Semaphore(config.LLM_CONCURRENCY)
    rule_text = "\n".join(f"- {r.summary}" for r in rules[:20]) if rules else "(无)"

    done = [0]

    async def run_one(chunk):
        async with semaphore:
            # 跳过太短的段落(不送 LLM)
            paragraph_payload = "\n\n".join(
                f"[paragraph_idx={p.paragraph_idx}]\n{p.text}"
                for p in chunk.paragraphs
                if p.text.strip() and len(p.text.strip()) >= config.MIN_PARAGRAPH_LEN
            )
            if not paragraph_payload:
                return []
            user_msg = (
                f"用户已确认规则:\n{rule_text}\n\n"
                f"上文上下文:\n{chunk.context_before or '无'}\n\n"
                f"下文上下文:\n{chunk.context_after or '无'}\n\n"
                f"待校对段落组:\n{paragraph_payload}"
            )
            try:
                raw = await llm.achat_json(prompts.FAST_SYSTEM, user_msg, max_tokens=3000)
            except Exception as e:
                print(f"[FAST/{chunk.paragraph_start}-{chunk.paragraph_end}] LLM 失败:{e}")
                return []
            errs = _parse_fast_result(raw, paragraphs, doc_id)
            done[0] += 1
            if on_progress:
                on_progress("L1-L3 LLM", done[0], len(chunks), errs)
            return errs

    results = await asyncio.gather(*(run_one(c) for c in chunks))
    return [e for batch in results for e in batch]


def _parse_fast_result(raw: Any, paragraphs: list[Paragraph], doc_id: str) -> list[ProofreadError]:
    text_by_idx = {p.paragraph_idx: p.text for p in paragraphs}
    out: list[ProofreadError] = []
    if not isinstance(raw, dict):
        return out
    for k, items in raw.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if idx not in text_by_idx or not isinstance(items, list):
            continue
        text = text_by_idx[idx]
        for item in items:
            try:
                cs, ce = int(item["char_start"]), int(item["char_end"])
                original = item["original"]
                if not (0 <= cs < ce <= len(text)) or text[cs:ce] != original:
                    pos = text.find(original)
                    if pos < 0:
                        continue
                    cs, ce = pos, pos + len(original)
                layer = item.get("layer", "L2")
                if layer not in ("L1", "L2", "L3"):
                    layer = "L2"
                out.append(ProofreadError(
                    id=uuid.uuid4().hex[:12],
                    doc_id=doc_id,
                    layer=Layer(layer),
                    type=item.get("type", "未分类"),
                    confidence=Confidence(item.get("confidence", "medium")),
                    paragraph_idx=idx,
                    char_start=cs, char_end=ce,
                    original=original,
                    suggestion=item.get("suggestion", ""),
                    explanation=item.get("explanation", ""),
                    metadata=ErrorMetadata(pass_id="FAST", prompt_version=prompts.PROMPT_VERSION),
                ))
            except (KeyError, ValueError, TypeError):
                continue
    return out


# ============================================================================
# Phase 3: L4 三步法
# ============================================================================
async def _run_l4(
    doc_id: str, paragraphs: list[Paragraph],
    on_progress: Callable | None = None,
) -> list[ProofreadError]:
    candidates = _l4_candidate_pairs(paragraphs, config.L4_CANDIDATE_LIMIT)
    if not candidates:
        return []
    if on_progress:
        on_progress("L4-候选", len(candidates), len(candidates), [])

    # 让 LLM 复核
    pairs_for_llm = [
        {
            "candidate_id": c["candidate_id"],
            "a": {"text": c["preferred"], "count": c["counts"][c["preferred"]],
                  "samples": [ev["snippet"] for ev in c["evidence"] if ev["term"] == c["preferred"]][:3]},
            "b": {"text": c["variant"], "count": c["counts"][c["variant"]],
                  "samples": [ev["snippet"] for ev in c["evidence"] if ev["term"] == c["variant"]][:3]},
        }
        for c in candidates
    ]
    user_msg = "候选对:\n" + str(pairs_for_llm) + "\n\n输出 JSON 数组。"
    try:
        raw = await llm.achat_json(prompts.L4_REVIEW_SYSTEM, user_msg, max_tokens=2000)
    except Exception as e:
        print(f"[L4 复核] LLM 失败:{e}")
        return []
    if not isinstance(raw, list):
        return []

    decisions = {item.get("candidate_id"): item for item in raw if isinstance(item, dict)}
    errors: list[ProofreadError] = []
    text_by_idx = {p.paragraph_idx: p.text for p in paragraphs}
    for cand in candidates:
        decision = decisions.get(cand["candidate_id"])
        if not decision or decision.get("type") != "merge":
            continue
        recommend = decision.get("recommend") or cand["preferred"]
        non_rec = cand["variant"] if recommend == cand["preferred"] else cand["preferred"]
        explanation = decision.get("explanation", "全文专名不一致建议统一")

        for occ in cand["occurrences"][non_rec]:
            para, start, end = occ
            if text_by_idx.get(para.paragraph_idx, "")[start:end] != non_rec:
                continue
            errors.append(ProofreadError(
                id=uuid.uuid4().hex[:12], doc_id=doc_id,
                layer=Layer.L4, type="专名不一致",
                confidence=Confidence.medium,
                paragraph_idx=para.paragraph_idx,
                char_start=start, char_end=end,
                original=non_rec, suggestion=recommend,
                explanation=explanation,
                metadata=ErrorMetadata(pass_id="L4", prompt_version=prompts.PROMPT_VERSION),
            ))
    return errors


_PROPER_NAME_SUFFIXES = (
    "大学", "中学", "小学", "学校", "医院", "公司", "报社", "晚报", "日报", "时报",
    "集团", "工厂", "车站", "码头",
    "村", "镇", "城", "市", "县", "区", "街", "路", "桥", "山", "河", "湖", "溪",
    "港", "湾", "寺", "庙", "馆", "园", "巷", "弄",
)

_WEAK_TERMS = {
    "时候", "一个", "我们", "他们", "今天", "明天", "昨天", "现在", "以前", "以后",
    "这里", "那里", "什么", "怎么", "为什么", "如何", "可能", "或者", "但是", "因为",
    "所以", "如果", "虽然", "然而", "并且", "而且", "因此", "于是", "然后", "接着",
}


def _l4_candidate_pairs(paragraphs: list[Paragraph], limit: int) -> list[dict[str, Any]]:
    """提取候选专名 + 按编辑距离 ≤ 1 聚类。"""
    occurrences: dict[str, list[tuple[Paragraph, int, int]]] = defaultdict(list)
    for paragraph in paragraphs:
        for start, end, term in _extract_terms(paragraph.text):
            if term in _WEAK_TERMS or len(term) < 2:
                continue
            occurrences[term].append((paragraph, start, end))

    # 按长度+末字分组,提升聚类效率
    groups: dict[tuple[int, str], list[str]] = defaultdict(list)
    for term in occurrences:
        groups[(len(term), term[-1])].append(term)

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group_terms in groups.values():
        for i, a in enumerate(group_terms):
            if len(candidates) >= limit:
                break
            for b in group_terms[i + 1:]:
                if len(candidates) >= limit:
                    break
                if _edit_distance(a, b) > 1:
                    continue
                pair = tuple(sorted((a, b)))
                if pair in seen:
                    continue
                seen.add(pair)
                preferred = a if len(occurrences[a]) >= len(occurrences[b]) else b
                variant = b if preferred == a else a
                candidates.append({
                    "candidate_id": f"l4-{len(candidates) + 1}",
                    "preferred": preferred,
                    "variant": variant,
                    "counts": {preferred: len(occurrences[preferred]),
                              variant: len(occurrences[variant])},
                    "occurrences": {preferred: occurrences[preferred], variant: occurrences[variant]},
                    "evidence": _make_evidence(preferred, occurrences[preferred])
                              + _make_evidence(variant, occurrences[variant]),
                })
        if len(candidates) >= limit:
            break
    return candidates


def _extract_terms(text: str) -> list[tuple[int, int, str]]:
    terms = []
    # 后缀地名/机构匹配
    for run_match in re.finditer(r"[一-鿿]{2,40}", text):
        run = run_match.group(0)
        base = run_match.start()
        for suffix in _PROPER_NAME_SUFFIXES:
            search_from = 0
            while True:
                idx = run.find(suffix, search_from)
                if idx < 0:
                    break
                end_in_run = idx + len(suffix)
                for term_len in range(max(3, len(suffix) + 1), min(10, end_in_run) + 1):
                    start_in_run = end_in_run - term_len
                    term = run[start_in_run:end_in_run]
                    terms.append((base + start_in_run, base + end_in_run, term))
                search_from = idx + 1
    # 《》书名 / 引号内人名
    for match in re.finditer(r"《[^》]{2,30}》", text):
        terms.append((match.start(), match.end(), match.group(0).strip("《》")))
    for match in re.finditer(r"[“\"]([^”\"]{2,12})[”\"]", text):
        terms.append((match.start(1), match.end(1), match.group(1)))
    return terms


def _make_evidence(term: str, occs: list[tuple[Paragraph, int, int]]) -> list[dict]:
    out = []
    for para, start, end in occs[:3]:
        ctx_start = max(0, start - 12)
        ctx_end = min(len(para.text), end + 12)
        out.append({"term": term, "snippet": para.text[ctx_start:ctx_end]})
    return out


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 1:
        return 2  # 短路
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
        prev = curr
    return prev[-1]


# ============================================================================
# L5 修订校验(接受时调用)
# ============================================================================
def l5_quick_check(doc_id: str, paragraph_idx: int, before_text: str, after_text: str) -> list[ProofreadError]:
    """Python 快检 5 类风险(毫秒)。"""
    if before_text == after_text:
        return []
    errors: list[ProofreadError] = []

    def add(type_: str, conf: str, msg: str):
        errors.append(ProofreadError(
            id=uuid.uuid4().hex[:12], doc_id=doc_id,
            layer=Layer.L5, type=type_,
            confidence=Confidence(conf),
            paragraph_idx=paragraph_idx, char_start=0,
            char_end=min(len(after_text), 30),
            original=after_text[:30] + ("…" if len(after_text) > 30 else ""),
            suggestion="",
            explanation=msg,
            metadata=ErrorMetadata(pass_id="L5-quick"),
        ))

    # 1. 拆固定词组
    for phrase in ("其时", "因此", "然而", "故此", "于是"):
        if phrase in before_text and phrase not in after_text and phrase[0] in after_text:
            add("固定词组被拆", "high", f"'{phrase}' 被拆,可能不成词,建议复核")
            break

    # 2. 删除后剩余不成词模式(如 五官分明 → 五官分)
    for m in re.finditer(r"([一-鿿])(分|地|的)([很非常实在])", after_text):
        add("删除后不成词", "medium", f"出现'{m.group(0)}'疑不成词,建议复核")
        break

    # 3. 连续重复标点
    if re.search(r"[，。;,;]{2,}|[!?！？]{3,}", after_text):
        add("重复标点", "high", "出现连续重复标点,可能是误删导致")

    # 4. 中文之间出现半角空格(新增的)
    if (re.search(r"[一-鿿] [一-鿿]", after_text)
            and not re.search(r"[一-鿿] [一-鿿]", before_text)):
        add("空格异常", "medium", "中文之间多了空格,建议删除")

    # 5. 删了句末标点导致两句粘连
    end_punct = ("。", "!", "?", "！", "？")
    if before_text.endswith(end_punct) and after_text and after_text[-1] not in end_punct:
        # 看 after 里面是不是粘成一长串没标点
        if not any(p in after_text for p in end_punct):
            add("语句断裂", "medium", "句末标点缺失,可能与下句粘连")

    return errors


async def l5_ai_check(doc_id: str, paragraph_idx: int, before: str, after: str) -> list[ProofreadError]:
    """LLM 复核(后台异步,可慢)。"""
    user = prompts.L5_USER_EVENT_TPL.format(before=before, after=after)
    try:
        raw = await llm.achat_json(prompts.L5_EVENT_SYSTEM, user, max_tokens=800)
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        try:
            out.append(ProofreadError(
                id=uuid.uuid4().hex[:12], doc_id=doc_id,
                layer=Layer.L5,
                type=f"修订校验:{item.get('type', '风险')}",
                confidence=Confidence(item.get("confidence", "medium")),
                paragraph_idx=paragraph_idx, char_start=0,
                char_end=min(len(after), 30),
                original=after[:30] + ("…" if len(after) > 30 else ""),
                suggestion="",
                explanation=(item.get("concern", "") + " | 建议:" + item.get("suggestion", "")).strip(" |"),
                metadata=ErrorMetadata(pass_id="L5-ai", prompt_version=prompts.PROMPT_VERSION),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return out


# ============================================================================
# 工具
# ============================================================================
def _filter_by_rules(errors: list[ProofreadError], rules: list[Any]) -> list[ProofreadError]:
    """简单实现:把规则 summary 关键词与 error.explanation/original 模糊比对,命中则过滤。"""
    if not rules:
        return errors
    keywords = set()
    for r in rules:
        for word in re.findall(r"[一-鿿]{2,}", r.summary):
            keywords.add(word)
    if not keywords:
        return errors
    kept = []
    for e in errors:
        haystack = e.original + e.explanation
        if any(kw in haystack for kw in keywords if len(kw) >= 3):
            continue
        kept.append(e)
    return kept


def _aggregate(errors: list[ProofreadError]) -> list[ProofreadError]:
    """同段同位置同 original 视为一个,优先高置信。"""
    seen: dict[tuple, ProofreadError] = {}
    rank = {Confidence.high: 3, Confidence.medium: 2, Confidence.low: 1}
    for e in errors:
        key = (e.paragraph_idx, e.char_start, e.char_end, e.original, e.layer.value)
        if key not in seen or rank[e.confidence] > rank[seen[key].confidence]:
            seen[key] = e
    return sorted(seen.values(), key=lambda e: (e.paragraph_idx, e.char_start))
