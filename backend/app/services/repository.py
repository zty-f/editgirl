"""数据访问层:封装所有 SQLite 操作。"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from ..core.store import get_conn, new_id
from ..schemas import (
    ChatMessage, Confidence, Document, ErrorMetadata, FindingSource,
    Layer, Paragraph, ProofreadError, ReviewStatus, Rule, RuleCandidate,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- documents ----------
def insert_document(filename: str, paragraphs: list[Paragraph],
                    file_path: str, work_path: str) -> Document:
    conn = get_conn()
    doc_id = new_id()
    word_count = sum(len(p.text) for p in paragraphs)
    created = now_iso()
    with conn:
        conn.execute(
            "INSERT INTO documents (id, filename, paragraph_count, word_count, file_path, work_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, filename, len(paragraphs), word_count, file_path, work_path, created),
        )
        conn.executemany(
            "INSERT INTO paragraphs (doc_id, paragraph_idx, text, style) VALUES (?, ?, ?, ?)",
            [(doc_id, p.paragraph_idx, p.text, p.style) for p in paragraphs],
        )
    return Document(
        id=doc_id, filename=filename, paragraph_count=len(paragraphs),
        word_count=word_count, file_path=file_path, created_at=created,
    )


def get_document(doc_id: str) -> Document | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        return None
    return Document(
        id=row["id"], filename=row["filename"],
        paragraph_count=row["paragraph_count"], word_count=row["word_count"],
        file_path=row["file_path"], created_at=row["created_at"],
    )


def get_document_work_path(doc_id: str) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT work_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return row["work_path"] if row else None


def list_documents(limit: int = 50) -> list[Document]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        Document(
            id=r["id"], filename=r["filename"],
            paragraph_count=r["paragraph_count"], word_count=r["word_count"],
            file_path=r["file_path"], created_at=r["created_at"],
        )
        for r in rows
    ]


def delete_document(doc_id: str) -> None:
    from pathlib import Path
    conn = get_conn()
    # 先拿文件路径
    row = conn.execute(
        "SELECT file_path, work_path FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    if row:
        for p in (row["file_path"], row["work_path"]):
            try:
                Path(p).unlink(missing_ok=True)
            except (OSError, TypeError):
                pass
    with conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ---------- paragraphs ----------
def get_paragraphs(doc_id: str) -> list[Paragraph]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT paragraph_idx, text, style FROM paragraphs WHERE doc_id = ? ORDER BY paragraph_idx",
        (doc_id,),
    ).fetchall()
    return [Paragraph(paragraph_idx=r["paragraph_idx"], text=r["text"], style=r["style"]) for r in rows]


# ---------- errors ----------
def _error_from_row(r) -> ProofreadError:
    return ProofreadError(
        id=r["id"], doc_id=r["doc_id"],
        layer=Layer(r["layer"]), type=r["type"],
        confidence=Confidence(r["confidence"]),
        paragraph_idx=r["paragraph_idx"],
        char_start=r["char_start"], char_end=r["char_end"],
        original=r["original"], suggestion=r["suggestion"],
        explanation=r["explanation"],
        status=ReviewStatus(r["status"]),
        source=FindingSource(r["source"]),
        user_feedback=r["user_feedback"],
        final_text=r["final_text"],
        metadata=ErrorMetadata(**json.loads(r["metadata"] or "{}")),
        created_at=r["created_at"],
    )


def insert_errors(errors: list[ProofreadError]) -> None:
    if not errors:
        return
    conn = get_conn()
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO errors (id, doc_id, layer, type, confidence, paragraph_idx, "
            "char_start, char_end, original, suggestion, explanation, status, source, "
            "user_feedback, final_text, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e.id, e.doc_id, e.layer.value, e.type, e.confidence.value,
                    e.paragraph_idx, e.char_start, e.char_end,
                    e.original, e.suggestion, e.explanation,
                    e.status.value, e.source.value, e.user_feedback, e.final_text,
                    json.dumps(e.metadata.model_dump(), ensure_ascii=False),
                    e.created_at,
                )
                for e in errors
            ],
        )


def get_error(error_id: str) -> ProofreadError | None:
    conn = get_conn()
    r = conn.execute("SELECT * FROM errors WHERE id = ?", (error_id,)).fetchone()
    return _error_from_row(r) if r else None


def list_errors(doc_id: str) -> list[ProofreadError]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM errors WHERE doc_id = ? ORDER BY paragraph_idx, char_start",
        (doc_id,),
    ).fetchall()
    return [_error_from_row(r) for r in rows]


def update_error_status(error_id: str, status: ReviewStatus,
                        final_text: str = "", user_feedback: str = "") -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE errors SET status=?, final_text=?, user_feedback=? WHERE id=?",
            (status.value, final_text, user_feedback, error_id),
        )


def state_summary(doc_id: str) -> dict[str, int]:
    conn = get_conn()
    row = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
        "  SUM(CASE WHEN status IN ('accepted','edited') THEN 1 ELSE 0 END) AS accepted, "
        "  SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) AS rejected, "
        "  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed, "
        "  COUNT(*) AS total "
        "FROM errors WHERE doc_id=?",
        (doc_id,),
    ).fetchone()
    return {
        "pending": row["pending"] or 0,
        "accepted": row["accepted"] or 0,
        "rejected": row["rejected"] or 0,
        "failed": row["failed"] or 0,
        "total": row["total"] or 0,
    }


# ---------- chat ----------
def insert_chat_message(doc_id: str, role: str, content: str,
                       metadata: dict[str, Any] | None = None) -> ChatMessage:
    conn = get_conn()
    msg_id = new_id()
    created = now_iso()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO chat_messages (id, doc_id, role, content, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, doc_id, role, content, meta_json, created),
        )
    return ChatMessage(id=msg_id, doc_id=doc_id, role=role, content=content,
                       metadata=metadata or {}, created_at=created)


def list_chat_messages(doc_id: str, limit: int = 200) -> list[ChatMessage]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE doc_id=? ORDER BY created_at ASC LIMIT ?",
        (doc_id, limit),
    ).fetchall()
    return [
        ChatMessage(
            id=r["id"], doc_id=r["doc_id"], role=r["role"], content=r["content"],
            metadata=json.loads(r["metadata"] or "{}"), created_at=r["created_at"],
        )
        for r in rows
    ]


# ---------- rules ----------
def _rule_from_row(r) -> Rule:
    return Rule(
        id=r["id"], summary=r["summary"], category=r["category"],
        examples=json.loads(r["examples"] or "[]"),
        hit_count=r["hit_count"], enabled=bool(r["enabled"]),
        created_at=r["created_at"], last_used=r["last_used"] or "",
    )


def upsert_rule(summary: str, category: str, examples: list[str] | None = None) -> Rule:
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM rules WHERE summary=? AND category=?", (summary.strip(), category)
    ).fetchone()
    if existing:
        new_examples = list(set(json.loads(existing["examples"] or "[]") + (examples or [])))
        with conn:
            conn.execute(
                "UPDATE rules SET hit_count=hit_count+1, examples=?, last_used=? WHERE id=?",
                (json.dumps(new_examples, ensure_ascii=False), now_iso(), existing["id"]),
            )
        return _rule_from_row(conn.execute("SELECT * FROM rules WHERE id=?", (existing["id"],)).fetchone())
    rule_id = new_id()
    created = now_iso()
    with conn:
        conn.execute(
            "INSERT INTO rules (id, summary, category, examples, hit_count, enabled, created_at, last_used) "
            "VALUES (?, ?, ?, ?, 1, 1, ?, ?)",
            (rule_id, summary.strip(), category, json.dumps(examples or [], ensure_ascii=False), created, created),
        )
    return Rule(id=rule_id, summary=summary.strip(), category=category,
                examples=examples or [], hit_count=1, enabled=True,
                created_at=created, last_used=created)


def list_rules(category: str | None = None) -> list[Rule]:
    conn = get_conn()
    if category:
        rows = conn.execute(
            "SELECT * FROM rules WHERE enabled=1 AND category IN (?, 'custom') ORDER BY hit_count DESC",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM rules WHERE enabled=1 ORDER BY hit_count DESC"
        ).fetchall()
    return [_rule_from_row(r) for r in rows]


def disable_rule(rule_id: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute("UPDATE rules SET enabled=0 WHERE id=?", (rule_id,))
    return cur.rowcount > 0


# ---------- rule candidates ----------
def insert_rule_candidate(summary: str, category: str, source: str,
                          evidence: list[str] | None = None) -> RuleCandidate:
    conn = get_conn()
    cid = new_id()
    created = now_iso()
    with conn:
        conn.execute(
            "INSERT INTO rule_candidates (id, summary, category, source, evidence, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
            (cid, summary, category, source, json.dumps(evidence or [], ensure_ascii=False), created),
        )
    return RuleCandidate(id=cid, summary=summary, category=category, source=source,
                         evidence=evidence or [], status="draft", created_at=created)


def list_rule_candidates(status: str = "draft") -> list[RuleCandidate]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM rule_candidates WHERE status=? ORDER BY created_at DESC", (status,)
    ).fetchall()
    return [
        RuleCandidate(
            id=r["id"], summary=r["summary"], category=r["category"],
            source=r["source"], evidence=json.loads(r["evidence"] or "[]"),
            status=r["status"], created_at=r["created_at"],
        )
        for r in rows
    ]


def approve_rule_candidate(candidate_id: str) -> Rule | None:
    conn = get_conn()
    r = conn.execute("SELECT * FROM rule_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not r:
        return None
    rule = upsert_rule(
        summary=r["summary"], category=r["category"],
        examples=json.loads(r["evidence"] or "[]"),
    )
    with conn:
        conn.execute("UPDATE rule_candidates SET status='approved' WHERE id=?", (candidate_id,))
    return rule


def archive_rule_candidate(candidate_id: str) -> bool:
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "UPDATE rule_candidates SET status='archived' WHERE id=?", (candidate_id,)
        )
    return cur.rowcount > 0
