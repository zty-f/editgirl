"""用户在前端创建的 Prompt Skill — 持久化到 SQLite。

数据流:
- 前端"+ 新建 Skill" → POST /api/user_skills → 入 user_skills 表
- skill_registry.list_all() 时把所有 user_skills 注册成 user.* skill
- 调度时每个 user skill 跑一次 LLM,把段落喂给用户写的 prompt
"""
from __future__ import annotations
import json
import uuid
import asyncio
from datetime import datetime, timezone
from ..core.store import get_conn
from ..schemas import ProofreadError, SkillContext, Layer, Confidence, ErrorMetadata, FindingSource


# ---------- CRUD ----------
def list_user_skills() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM user_skills ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_user_skill(skill_id: str) -> dict | None:
    conn = get_conn()
    r = conn.execute("SELECT * FROM user_skills WHERE id=?", (skill_id,)).fetchone()
    return dict(r) if r else None


def create_user_skill(name: str, description: str, prompt: str, phase: int = 50) -> dict:
    conn = get_conn()
    sid = uuid.uuid4().hex[:12]
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            "INSERT INTO user_skills (id, name, description, prompt, phase, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (sid, name, description, prompt, phase, created),
        )
    return get_user_skill(sid)


def update_user_skill(skill_id: str, **fields) -> dict | None:
    if not fields:
        return get_user_skill(skill_id)
    allowed = {"name", "description", "prompt", "phase", "enabled"}
    sets = []
    vals = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k}=?")
        vals.append(int(v) if k in ("phase", "enabled") and isinstance(v, bool) else v)
    if not sets:
        return get_user_skill(skill_id)
    vals.append(skill_id)
    conn = get_conn()
    with conn:
        conn.execute(f"UPDATE user_skills SET {','.join(sets)} WHERE id=?", vals)
    return get_user_skill(skill_id)


def delete_user_skill(skill_id: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM user_skills WHERE id=?", (skill_id,))
    return cur.rowcount > 0


# ---------- 运行 user prompt skill ----------
async def run_user_prompt_skill(prompt: str, ctx: SkillContext) -> list[ProofreadError]:
    """把全文段落喂给用户的 prompt,让 LLM 返回 JSON findings 数组。"""
    from . import llm
    paragraphs_text = "\n\n".join(
        f"[paragraph_idx={p.paragraph_idx}]\n{p.text}"
        for p in ctx.paragraphs if p.text.strip()
    )
    # 用户的 prompt 当 system,加一个统一输出契约
    system = prompt + """

【输出格式 — 严格 JSON】
{"5":[{"char_start":3,"char_end":4,"original":"颤","suggestion":"战","explanation":"...","confidence":"high"}],"7":[]}

key=段号字符串。char_start/end 是段内字符偏移。original 必须 == 原文对应字符串。
无问题段输出 [] 或省略。仅输出 JSON 对象。"""
    user = f"待校对段落:\n\n{paragraphs_text}\n\n输出 JSON 对象。"
    try:
        raw = await llm.achat_json(system, user, max_tokens=3000)
    except Exception as e:
        print(f"[user skill] LLM 失败: {e}")
        return []
    if not isinstance(raw, dict):
        return []

    text_by_idx = {p.paragraph_idx: p.text for p in ctx.paragraphs}
    out = []
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
                out.append(ProofreadError(
                    id=uuid.uuid4().hex[:12], doc_id=ctx.doc_id,
                    layer=Layer.USER, type="用户 Skill",
                    confidence=Confidence(item.get("confidence", "medium")),
                    paragraph_idx=idx, char_start=cs, char_end=ce,
                    original=original, suggestion=item.get("suggestion", ""),
                    explanation=item.get("explanation", ""),
                    source=FindingSource.auto,
                    metadata=ErrorMetadata(pass_id="user_skill"),
                ))
            except (KeyError, ValueError, TypeError):
                continue
    return out
