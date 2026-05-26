"""LLM 配置 + 其它运行时设置 — SQLite key-value 表。

优先级:DB settings > 启动时 .env。
前端改了 settings → 立即在下次 LLM 调用生效。
"""
from __future__ import annotations
from ..core.store import get_conn
from ..core import config as _env_defaults


KEYS = ("LLM_PROVIDER", "OPENAI_BASE_URL", "OPENAI_API_KEY", "LLM_MODEL")


def get_settings() -> dict[str, str]:
    """合并 .env 默认 + DB 覆盖。"""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    overrides = {r["key"]: r["value"] for r in rows}
    return {
        "LLM_PROVIDER": overrides.get("LLM_PROVIDER", "openai"),  # openai | anthropic
        "OPENAI_BASE_URL": overrides.get("OPENAI_BASE_URL", _env_defaults.OPENAI_BASE_URL),
        "OPENAI_API_KEY": overrides.get("OPENAI_API_KEY", _env_defaults.OPENAI_API_KEY),
        "LLM_MODEL": overrides.get("LLM_MODEL", _env_defaults.LLM_MODEL),
    }


def update_settings(payload: dict) -> dict:
    conn = get_conn()
    with conn:
        for k, v in payload.items():
            if k not in KEYS:
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )
    return get_settings()


def get_masked() -> dict:
    """给前端展示时,API Key 部分遮挡。"""
    s = get_settings()
    key = s["OPENAI_API_KEY"]
    masked = (key[:4] + "***" + key[-2:]) if len(key) > 7 else "***"
    return {
        "LLM_PROVIDER": s["LLM_PROVIDER"],
        "OPENAI_BASE_URL": s["OPENAI_BASE_URL"],
        "OPENAI_API_KEY_masked": masked,
        "LLM_MODEL": s["LLM_MODEL"],
    }
