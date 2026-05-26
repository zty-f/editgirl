"""校对完成 / 操作密集后,Agent 主动给 1-3 条下一步建议。"""
from __future__ import annotations
import asyncio
from collections import Counter
from . import llm
from ..schemas import ProofreadError, ReviewStatus


REC_SYSTEM = """你是图书校对助理。校对刚跑完,你看到 findings 统计。请给 1-3 条**具体可行**的下一步建议,告诉用户接下来该点哪个按钮。

【可建议的动作】
- 🏷️ 跑 L4 专名一致性(如有人名/地名疑似)
- 🔄 跑 L5 修订校验(已接受较多修改)
- ✓ 批量接受全部高置信
- 📚 用对话教规则(某类问题密集)
- 👀 重点看某层 / 某段

【规则】
- 别套话,每条 ≤ 50 字
- 数据弱时(<3 处)别瞎推,只说"问题不多,逐条 review"
- 用 emoji 对应按钮

【输出】
JSON 数组,1-3 条:
[{"emoji":"🏷️","text":"..."}]

仅输出 JSON 数组。"""


async def arecommend(errors: list[ProofreadError]) -> list[dict]:
    pending = [e for e in errors if e.status == ReviewStatus.pending]
    if len(pending) < 3:
        return []
    by_layer = Counter(e.layer.value for e in pending)
    by_conf = Counter(e.confidence.value for e in pending)
    by_type = Counter(e.type for e in pending)
    by_para = Counter(e.paragraph_idx for e in pending)
    hot = [idx for idx, n in by_para.most_common(3) if n >= 3]

    accepted = sum(1 for e in errors if e.status in (ReviewStatus.accepted, ReviewStatus.edited))
    rejected = sum(1 for e in errors if e.status == ReviewStatus.rejected)

    summary = (
        f"【统计】待 {len(pending)},接受 {accepted},拒绝 {rejected}\n"
        f"分层:{dict(by_layer)}\n"
        f"置信度:{dict(by_conf)}\n"
        f"类型 top5:{dict(by_type.most_common(5))}\n"
        f"热点段落:{hot or '无'}"
    )
    try:
        result = await llm.achat_json(REC_SYSTEM, summary, max_tokens=400)
    except Exception:
        return []
    return result[:3] if isinstance(result, list) else []


def recommend(errors: list[ProofreadError]) -> list[dict]:
    return asyncio.run(arecommend(errors))


def format_for_chat(recs: list[dict]) -> str:
    if not recs:
        return ""
    lines = ["📋 下一步建议:"]
    for r in recs:
        lines.append(f"  {r.get('emoji', '·')} {r.get('text', '')}")
    return "\n".join(lines)
