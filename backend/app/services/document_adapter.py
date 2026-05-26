"""Docx 加载、track-changes 应用、预览渲染。

从旧版 docx_session 演化:不再持有 in-memory 会话状态(改靠 SQLite + 工作 docx 文件)。
"""
from __future__ import annotations
import shutil
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from docx_revisions import RevisionDocument

from ..schemas import Paragraph, ProofreadError, ReviewStatus
from .repository import get_document_work_path


def load_docx_paragraphs(path: str | Path) -> list[Paragraph]:
    """从 docx 提取段落(供 NER/校对/持久化)。"""
    rdoc = RevisionDocument(str(path))
    out: list[Paragraph] = []
    for i, p in enumerate(rdoc.paragraphs):
        style = p.style.name if p.style else "Normal"
        out.append(Paragraph(paragraph_idx=i, text=p.text, style=style))
    return out


def copy_to_work(src: str | Path, work_path: str | Path) -> Path:
    """把上传的 docx 复制一份到 work 目录,作为修订工作副本。"""
    work_path = Path(work_path)
    work_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, work_path)
    return work_path


def _minimal_diff_spans(original: str, suggestion: str) -> list[tuple[int, int, str]]:
    matcher = SequenceMatcher(None, original, suggestion, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        out.append((i1, i2, suggestion[j1:j2]))
    return out


def apply_revision(doc_id: str, error: ProofreadError, final_text: str | None = None,
                   author: str = "校对女孩") -> tuple[ReviewStatus, str]:
    """在工作 docx 上应用一条修订(track changes)。

    返回 (新状态, 信息)。失败时返回 (failed, 原因)。
    """
    target = final_text if final_text is not None else error.suggestion
    work_path = get_document_work_path(doc_id)
    if not work_path:
        return ReviewStatus.failed, "文档不存在"

    rdoc = RevisionDocument(work_path)
    if error.paragraph_idx >= len(rdoc.paragraphs):
        return ReviewStatus.failed, f"段落 {error.paragraph_idx} 越界"

    para = rdoc.paragraphs[error.paragraph_idx]
    comment = error.explanation or None

    spans = _minimal_diff_spans(error.original, target)
    if not spans:
        return ReviewStatus.accepted, "无变化"

    has_pure_insert = any(s == e for s, e, _ in spans)
    if has_pure_insert:
        return _apply_whole(rdoc, work_path, para, error, target, author, comment, final_text)

    spans_sorted = sorted(spans, key=lambda s: -s[0])
    applied = 0
    last_error = None
    for local_start, local_end, replacement in spans_sorted:
        abs_start = error.char_start + local_start
        abs_end = error.char_start + local_end
        try:
            para.replace_tracked_at(
                abs_start, abs_end, replacement,
                author=author, index_mode="accepted",
                comment=comment if applied == 0 else None,
            )
            applied += 1
        except Exception as e:
            last_error = e

    if applied == 0:
        return _apply_whole(rdoc, work_path, para, error, target, author, comment, final_text)

    rdoc.save(work_path)
    n_chars = sum(e - s for s, e, _ in spans_sorted)
    status = ReviewStatus.edited if final_text is not None and final_text != error.suggestion else ReviewStatus.accepted
    return status, f"已应用 (只标 {n_chars} 字)"


def _apply_whole(rdoc, work_path, para, error, target, author, comment, final_text):
    try:
        para.replace_tracked_at(
            error.char_start, error.char_end, target,
            author=author, index_mode="accepted", comment=comment,
        )
    except Exception:
        try:
            count = para.replace_tracked(
                error.original, target,
                author=author, index_mode="accepted", comment=comment,
            )
            if count == 0:
                return ReviewStatus.failed, "找不到原文(可能与已有修订重叠)"
        except Exception as e:
            return ReviewStatus.failed, f"{type(e).__name__}: {e}"
    rdoc.save(work_path)
    status = ReviewStatus.edited if final_text is not None and final_text != error.suggestion else ReviewStatus.accepted
    return status, "已应用(整段)"


def render_preview(doc_id: str) -> dict:
    """读工作 docx,渲染成前端可用的 JSON。"""
    work_path = get_document_work_path(doc_id)
    if not work_path:
        return {"paragraphs": []}
    rdoc = RevisionDocument(work_path)
    out = []
    for i, para in enumerate(rdoc.paragraphs):
        style = para.style.name if para.style else "Normal"
        runs = []
        for item in para.iter_inner_content(include_revisions=True):
            cls = type(item).__name__
            text = getattr(item, "text", "") or ""
            if cls == "TrackedInsertion":
                runs.append({"type": "ins", "text": text})
            elif cls == "TrackedDeletion":
                runs.append({"type": "del", "text": text})
            else:
                if text:
                    runs.append({"type": "text", "text": text})
        out.append({"idx": i, "style": style, "runs": runs})
    return {"paragraphs": out}


def rebuild_work_docx_from_errors(doc_id: str, src_path: str, work_path: str,
                                  errors: list[ProofreadError]) -> None:
    """从原始 docx 重建工作副本并重放所有 accepted/edited 错误(用于 undo)。"""
    shutil.copy(src_path, work_path)
    rdoc = RevisionDocument(work_path)
    applied = [e for e in errors if e.status in (ReviewStatus.accepted, ReviewStatus.edited)]
    applied.sort(key=lambda e: (e.paragraph_idx, -e.char_start))
    for e in applied:
        target = e.final_text or e.suggestion
        if e.paragraph_idx >= len(rdoc.paragraphs):
            continue
        para = rdoc.paragraphs[e.paragraph_idx]
        try:
            para.replace_tracked_at(
                e.char_start, e.char_end, target,
                author="校对女孩", index_mode="accepted",
            )
        except (ValueError, IndexError):
            para.replace_tracked(e.original, target, author="校对女孩", index_mode="accepted")
    rdoc.save(work_path)


def get_paragraph_accepted_text(doc_id: str, paragraph_idx: int) -> tuple[str, str]:
    """返回 (原文, 接受所有修订后的文本) — L5 校验用。"""
    work_path = get_document_work_path(doc_id)
    if not work_path:
        return "", ""
    rdoc = RevisionDocument(work_path)
    if paragraph_idx >= len(rdoc.paragraphs):
        return "", ""
    para = rdoc.paragraphs[paragraph_idx]
    return para.original_text, para.accepted_text
