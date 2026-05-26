"""声明级 skill(不在 proofread 主 pipeline 里)。

L5/chat/export/rule_memory 不通过 pipeline 调度,但是这个智能体的能力,需要在 /api/skills 列出来给用户看。
"""
from app.services.skill_registry import register_skill


register_skill(
    id="builtin.l1_via_fast_pass",
    name="L1 字面错(在 Fast Pass 内)",
    description="错别字 / 标点 / 全半角等 L1 字面错由 FAST_SYSTEM LLM 抓,与 L2/L3 共用一次调用",
    layers=["L1"], scope="builtin", phase=15,
    runner=None,  # 不独立调度,合并在 L1-L3 Fast Pass 里
)

register_skill(
    id="builtin.editorial_baseline_l0",
    name="L0 三审三校基础规范",
    description="出版业三审三校 + 文学/非虚构/学术通用审稿底线,所有 LLM prompt 引用",
    layers=["L0"], scope="builtin", phase=5,
    runner=None,  # 嵌在 FAST_SYSTEM 里,不独立调度
)

register_skill(
    id="builtin.l5_revision_guard",
    name="L5 修订安全复核",
    description="用户接受/编辑时触发:Python 快检 5 类风险 + 后台 LLM 复核;导出前阻断",
    layers=["L5"], scope="builtin", phase=80,
    runner=None,  # 由 accept 接口触发,不在 proofread pipeline 里
)

register_skill(
    id="builtin.chat_agent",
    name="对话式修改 / 教规则",
    description="自然语言对话,LLM 规划:'把 X 改成 Y' / 教学规则 / 解释建议",
    layers=["chat"], scope="builtin", phase=90,
    runner=None,
)

register_skill(
    id="builtin.rule_memory",
    name="用户规则记忆",
    description="拒绝/编辑/对话 → 规则草案 → 用户确认 → 入库,下次校对自动避开",
    layers=["learn"], scope="builtin", phase=91,
    runner=None,
)

register_skill(
    id="builtin.word_track_changes_export",
    name="Word 修订导出",
    description="Word 原生 track changes(<w:ins>/<w:del>)+ 最小化 diff 标注 + 导出前 L5 阻断",
    layers=["export"], scope="builtin", phase=99,
    runner=None,
)
