"""L4 专名一致性 — Python 候选提取 + 编辑距离聚类 + LLM 复核三步法。

phase=30 → L1-L3 之后跑。
"""
from app.core import config
from app.schemas import ProofreadError, SkillContext
from app.services.skill_registry import register_decorator
from app.services import proofreader


@register_decorator(
    id="builtin.l4_consistency",
    name="L4 专名一致性",
    description="后缀匹配/引号/书名提取候选 + 编辑距离聚类 + LLM 复核疑似不一致专名",
    layers=["L4"],
    phase=30,
)
async def run(ctx: SkillContext) -> list[ProofreadError]:
    if not config.USE_LLM or not config.ENABLE_L4:
        return []
    return await proofreader._run_l4(ctx.doc_id, ctx.paragraphs, ctx.on_progress)
