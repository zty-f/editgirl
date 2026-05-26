"""配置:从 backend/.env 读 LLM 端点 + 路径。"""
from __future__ import annotations
import os
from pathlib import Path

# backend/ 根
BACKEND_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = BACKEND_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
WORK_DIR = DATA_DIR / "work"


def _load_env():
    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_env()

OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-5.5")

# 校对引擎参数(可在 .env 调)
USE_LLM = os.environ.get("USE_LLM", "true").lower() == "true"
ENABLE_L4 = os.environ.get("ENABLE_L4", "true").lower() == "true"
ENABLE_L5_AI = os.environ.get("ENABLE_L5_AI", "true").lower() == "true"
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "12"))
LLM_CHUNK_CHARS = int(os.environ.get("LLM_CHUNK_CHARS", "2400"))
L4_CANDIDATE_LIMIT = int(os.environ.get("L4_CANDIDATE_LIMIT", "30"))
MIN_PARAGRAPH_LEN = int(os.environ.get("MIN_PARAGRAPH_LEN", "8"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)
