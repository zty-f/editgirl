"""L1-L3 Fast LLM Pass — 合并一次 LLM 调用,按 chunk 并发。

phase=20 → L1 规则之后跑。
"""
from app.core import config
from app.schemas import ProofreadError, SkillContext
from app.services.skill_registry import register_decorator
from app.services import proofreader


@register_decorator(
    id="builtin.l1_l3_fast_pass",
    name="L1-L3 Fast LLM 校对",
    description=f"一次 LLM 调用合并 L1 补漏 + L2 冗余 + L3 语病(chunk={config.LLM_CHUNK_CHARS}, 并发={config.LLM_CONCURRENCY})",
    layers=["L1", "L2", "L3"],
    phase=20,
)
async def run(ctx: SkillContext) -> list[ProofreadError]:
    if not config.USE_LLM:
        return []
    return await proofreader._run_fast_pass(
        ctx.doc_id, ctx.paragraphs, ctx.user_rules, ctx.on_progress,
    )
