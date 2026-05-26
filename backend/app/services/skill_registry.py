"""Skill 注册表 + 调度器(可插拔)。

设计:
- Skill.runner 是真正干活的 callable:async def runner(ctx: SkillContext) -> list[ProofreadError]
- 调度时:遍历 enabled + 按 phase 排序的 skill,串/并行调用
- 注册新 skill = 1 行代码(写好 runner 后 register_skill 一次)

零代码加 skill:把模块放到 app/skills/<name>.py,导入即注册(__init__.py 自动 import)
"""
from __future__ import annotations
import asyncio
import importlib
import pkgutil
from typing import Awaitable, Callable
from ..schemas import ProofreadError, Skill, SkillContext


_REGISTRY: dict[str, Skill] = {}


def register_skill(
    *,
    id: str,
    name: str,
    description: str,
    layers: list[str],
    scope: str = "builtin",
    phase: int = 50,
    runner: Callable[[SkillContext], Awaitable[list[ProofreadError]]] | None = None,
) -> Skill:
    """注册一个 skill。runner 是异步函数。

    用法示例:
        @register_decorator(id="my_skill", phase=40, layers=["L6"], ...)
        async def my_runner(ctx: SkillContext) -> list[ProofreadError]:
            ...
    """
    skill = Skill(
        id=id, name=name, description=description, layers=layers,
        scope=scope, phase=phase, runner=runner,
    )
    _REGISTRY[id] = skill
    return skill


def register_decorator(**meta):
    """装饰器版本:@register_decorator(id=..., layers=...) 修饰 runner 函数。"""
    def deco(fn):
        register_skill(runner=fn, **meta)
        return fn
    return deco


def get(skill_id: str) -> Skill | None:
    return _REGISTRY.get(skill_id)


def list_all() -> list[Skill]:
    _refresh_user_skills()
    skills = list(_REGISTRY.values())
    _apply_persisted_state(skills)
    return sorted(skills, key=lambda s: s.phase)


def _refresh_user_skills() -> None:
    """把 user_skills 表里所有 skill 重新注册到 _REGISTRY,以反映前端最新增删改。"""
    try:
        from . import user_skills as _us
        from functools import partial
        # 先把旧的 user.* 清掉(可能被删了或改了)
        for sid in list(_REGISTRY.keys()):
            if sid.startswith("user."):
                del _REGISTRY[sid]
        for row in _us.list_user_skills():
            sid = f"user.{row['id']}"
            _REGISTRY[sid] = Skill(
                id=sid,
                name=row["name"],
                description=row["description"] or "(用户创建)",
                layers=["user"],
                scope="user",
                phase=row["phase"],
                enabled=bool(row["enabled"]),
                runner=partial(_us.run_user_prompt_skill, row["prompt"]),
            )
    except Exception as e:
        print(f"[user skills] 加载失败: {e}")


def list_runnable() -> list[Skill]:
    return [s for s in list_all() if s.enabled and s.runner is not None]


def _apply_persisted_state(skills: list[Skill]) -> None:
    """从 SQLite skill_state 表读最新 enabled,覆盖到内存。"""
    try:
        from ..core.store import get_conn
        conn = get_conn()
        rows = conn.execute("SELECT skill_id, enabled FROM skill_state").fetchall()
        state = {r["skill_id"]: bool(r["enabled"]) for r in rows}
        for s in skills:
            if s.id in state:
                s.enabled = state[s.id]
    except Exception:
        pass  # 表还没建时静默


def set_enabled(skill_id: str, enabled: bool) -> bool:
    """前端开关 → 持久化到 SQLite,下次 run_pipeline 立即生效。"""
    if skill_id not in _REGISTRY:
        return False
    from ..core.store import get_conn
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO skill_state (skill_id, enabled) VALUES (?, ?) "
            "ON CONFLICT(skill_id) DO UPDATE SET enabled=excluded.enabled",
            (skill_id, 1 if enabled else 0),
        )
    _REGISTRY[skill_id].enabled = enabled
    return True


async def run_pipeline(ctx: SkillContext) -> list[ProofreadError]:
    """按 phase 顺序执行所有可执行的 skill,聚合结果。"""
    all_errors: list[ProofreadError] = []
    for skill in list_runnable():
        try:
            errs = await skill.runner(ctx)  # type: ignore
            if errs:
                all_errors.extend(errs)
        except Exception as e:
            print(f"[skill {skill.id}] 失败:{type(e).__name__}: {e}")
    return all_errors


# ============================================================================
# 自动发现 skills/ 目录下的模块(零代码加 skill 的关键)
# ============================================================================
def autodiscover() -> None:
    """import app.skills 下所有模块,触发它们的 register_skill 调用。"""
    try:
        from .. import skills as skills_pkg
    except ImportError:
        return
    for _, name, _ in pkgutil.iter_modules(skills_pkg.__path__):
        importlib.import_module(f"app.skills.{name}")


# 启动时跑一次
autodiscover()
