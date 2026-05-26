"""SQLite 连接管理 + 建表。"""
from __future__ import annotations
import sqlite3
import threading
import uuid
from pathlib import Path
from .config import DATA_DIR


DB_PATH = DATA_DIR / "editgirl.db"
_local = threading.local()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def get_conn() -> sqlite3.Connection:
    """每个线程一个连接(SQLite 线程亲和)。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0,
    file_path TEXT NOT NULL,
    work_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paragraphs (
    doc_id TEXT NOT NULL,
    paragraph_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    style TEXT NOT NULL DEFAULT 'Normal',
    PRIMARY KEY (doc_id, paragraph_idx),
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS errors (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    paragraph_idx INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    original TEXT NOT NULL,
    suggestion TEXT NOT NULL DEFAULT '',
    explanation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL DEFAULT 'auto',
    user_feedback TEXT NOT NULL DEFAULT '',
    final_text TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_errors_doc ON errors(doc_id);
CREATE INDEX IF NOT EXISTS idx_errors_status ON errors(doc_id, status);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_doc ON chat_messages(doc_id, created_at);

CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    category TEXT NOT NULL,
    examples TEXT NOT NULL DEFAULT '[]',
    hit_count INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_used TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rule_candidates (
    id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_state (
    skill_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    phase INTEGER NOT NULL DEFAULT 50,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    conn = get_conn()
    with conn:
        conn.executescript(SCHEMA)
