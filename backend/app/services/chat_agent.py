"""对话式校对 Agent — 简化版(规则解析优先 + LLM 兜底,zcheck 风格)。

用户消息处理流程:
1. 优先识别确定性指令:"把X改成Y" / "删除X" / "以后...不要..."
2. 不能识别 → 走 LLM CHAT_SYSTEM 规划:返回 reply + edits + rule_candidates
3. 持久化所有消息到 chat_messages 表

返回:
- assistant 文本回复
- 新增的 edits(作为 chat 来源的 finding)
- 新增的 rule_candidates(待用户确认)
"""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone

from ..core import config
from ..schemas import Confidence, ErrorMetadata, FindingSource, Layer, ProofreadError, ReviewStatus, Paragraph
from . import llm, prompts, repository


_DIRECT_EDIT_PATTERNS = [
    re.compile(r"(?:把|将)\s*['\"“‘]?(?P<orig>.{1,40}?)['\"”’]?\s*改(?:成|为)\s*['\"“‘]?(?P<new>.{1,40}?)['\"”’]?[\s。.!?,，;；]*$"),
    re.compile(r"(?P<orig>.{1,40}?)\s*改(?:成|为)\s*(?P<new>.{1,40})"),
    re.compile(r"删除?\s*['\"“‘]?(?P<orig>.{1,40}?)['\"”’]?$"),
]


def _parse_direct_edits(message: str, paragraphs: list[Paragraph]) -> list[ProofreadError]:
    """从用户消息抽 '把X改成Y' / '删除X' 等明确指令。"""
    msg = message.strip()
    edits = []

    for pat in _DIRECT_EDIT_PATTERNS:
        m = pat.search(msg)
        if not m:
            continue
        orig = m.group("orig").strip(" 。.!?,，;；")
        new = (m.groupdict().get("new") or "").strip(" 。.!?,，;；")
        if not orig:
            continue
        # 在所有段落里找 first match
        for p in paragraphs:
            pos = p.text.find(orig)
            if pos >= 0:
                edits.append(_make_chat_edit(p, pos, pos + len(orig), orig, new,
                                            reason="对话指令"))
                return edits  # 一次只接受一个指令,避免歧义
    return edits


def _make_chat_edit(paragraph: Paragraph, start: int, end: int,
                    original: str, suggestion: str, reason: str,
                    source: FindingSource = FindingSource.chat) -> ProofreadError:
    return ProofreadError(
        id=uuid.uuid4().hex[:12],
        doc_id="",  # 调用方填
        layer=Layer.CHAT if source == FindingSource.chat else Layer.USER,
        type="对话建议" if source == FindingSource.chat else "用户直接修改",
        confidence=Confidence.medium if source == FindingSource.chat else Confidence.high,
        paragraph_idx=paragraph.paragraph_idx,
        char_start=start, char_end=end,
        original=original, suggestion=suggestion,
        explanation=reason,
        source=source,
        metadata=ErrorMetadata(pass_id="CHAT"),
    )


async def respond(
    doc_id: str, message: str, paragraphs: list[Paragraph],
    rules: list = None, recent_messages: list = None,
) -> dict:
    """处理一条用户消息,返回 {reply, new_edits, new_candidates}。

    new_edits / new_candidates 由调用方负责入库。
    """
    # 持久化用户消息
    repository.insert_chat_message(doc_id, "user", message)

    new_edits: list[ProofreadError] = []
    new_candidates: list[dict] = []
    reply_text = ""

    # 1. 优先确定性解析
    direct = _parse_direct_edits(message, paragraphs)
    if direct:
        for e in direct:
            e.doc_id = doc_id
        new_edits.extend(direct)
        reply_text = f"已加入 {len(direct)} 条对话建议到右侧待处理。请审核。"

    # 2. LLM 规划(找不到确定性指令 / 教学规则等场景)
    if config.USE_LLM:
        try:
            plan = await _run_chat_llm(message, paragraphs, rules or [], recent_messages or [])
        except Exception as e:
            plan = {"reply": f"对话规划失败:{e}", "edits": [], "rule_candidates": []}
    else:
        plan = {"reply": "", "edits": [], "rule_candidates": []}

    # 合并 LLM 输出
    if plan.get("reply") and not reply_text:
        reply_text = plan["reply"]
    elif plan.get("reply"):
        reply_text += "\n" + plan["reply"]

    for ed in plan.get("edits", []):
        try:
            idx = int(ed["paragraph_idx"])
            original = ed["original"]
            suggestion = ed.get("suggestion", "")
            reason = ed.get("reason", "对话建议")
            para = next((p for p in paragraphs if p.paragraph_idx == idx), None)
            if not para:
                continue
            pos = para.text.find(original)
            if pos < 0:
                continue
            e = _make_chat_edit(para, pos, pos + len(original), original, suggestion, reason)
            e.doc_id = doc_id
            new_edits.append(e)
        except (KeyError, TypeError, ValueError):
            continue

    for rc in plan.get("rule_candidates", []):
        try:
            new_candidates.append({
                "summary": rc["summary"],
                "category": rc.get("category", "custom"),
                "source": "chat_teaching",
                "evidence": [rc.get("evidence", message)],
            })
        except (KeyError, TypeError):
            continue

    # 持久化助手回复
    if not reply_text:
        reply_text = "(已收到)"
    repository.insert_chat_message(doc_id, "assistant", reply_text, metadata={
        "new_edits": len(new_edits),
        "new_candidates": len(new_candidates),
    })

    return {
        "reply": reply_text,
        "new_edits": new_edits,
        "new_candidates": new_candidates,
    }


async def _run_chat_llm(message: str, paragraphs: list[Paragraph],
                        rules: list, recent_messages: list) -> dict:
    rule_text = "\n".join(f"- {r.summary}" for r in rules[:10]) or "(无)"
    history_text = "\n".join(f"{m.role}: {m.content[:200]}" for m in recent_messages[-6:]) or "(无)"
    # 给 LLM 看前 60 段(避免 token 过大)
    para_text = "\n".join(
        f"[{p.paragraph_idx}] {p.text[:100]}{'...' if len(p.text) > 100 else ''}"
        for p in paragraphs[:60] if p.text.strip()
    )
    user = (
        f"用户当前消息:\n{message}\n\n"
        f"用户已有规则(参考,别违反):\n{rule_text}\n\n"
        f"最近对话(参考):\n{history_text}\n\n"
        f"文档段落(前 60 段预览):\n{para_text}\n\n"
        "输出 JSON 对象。"
    )
    return await llm.achat_json(prompts.CHAT_SYSTEM, user, max_tokens=1200)
