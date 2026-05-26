"""所有 REST API 路由 + WS。"""
from __future__ import annotations
import asyncio
import uuid
from functools import partial
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from dataclasses import asdict

from ..core import config
from ..core.store import init_db
from ..schemas import FindingSource, Layer, Confidence, ErrorMetadata, ProofreadError, ReviewStatus
from ..services import (
    document_adapter, proofreader, repository, recommendations,
    chat_agent, skill_registry, llm, settings_store, user_skills,
)
from ..services.skill_registry import list_all as list_skills

router = APIRouter()


# ============ WebSocket 连接登记(用于服务端 push 进度) ============
WS_CONNECTIONS: dict[str, WebSocket] = {}
MAIN_LOOP: asyncio.AbstractEventLoop | None = None


def push_ws(doc_id: str, msg: dict) -> None:
    ws = WS_CONNECTIONS.get(doc_id)
    if not ws or MAIN_LOOP is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(ws.send_json(msg), MAIN_LOOP)
    except Exception:
        pass


# ============ documents ============
@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "只支持 .docx")
    doc_id = uuid.uuid4().hex[:12]
    safe = f"{doc_id}_{file.filename}"
    file_path = config.UPLOADS_DIR / safe
    work_path = config.WORK_DIR / safe
    content = await file.read()
    file_path.write_bytes(content)
    document_adapter.copy_to_work(file_path, work_path)

    paragraphs = document_adapter.load_docx_paragraphs(file_path)
    doc = repository.insert_document(
        filename=file.filename,
        paragraphs=paragraphs,
        file_path=str(file_path),
        work_path=str(work_path),
    )
    return {
        "id": doc.id, "filename": doc.filename,
        "paragraph_count": doc.paragraph_count,
        "word_count": doc.word_count,
        "created_at": doc.created_at,
    }


@router.get("/documents")
async def list_docs():
    docs = repository.list_documents(limit=50)
    return [d.model_dump() for d in docs]


@router.get("/documents/{doc_id}")
async def get_doc(doc_id: str):
    doc = repository.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    return doc.model_dump()


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: str):
    repository.delete_document(doc_id)
    return {"ok": True}


@router.get("/documents/{doc_id}/preview")
async def preview(doc_id: str):
    if not repository.get_document(doc_id):
        raise HTTPException(404)
    return document_adapter.render_preview(doc_id)


@router.get("/documents/{doc_id}/download")
async def download(doc_id: str):
    work_path = repository.get_document_work_path(doc_id)
    if not work_path:
        raise HTTPException(404)
    doc = repository.get_document(doc_id)
    return FileResponse(
        work_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=doc.filename if doc else "edited.docx",
    )


# ============ proofread ============
@router.post("/documents/{doc_id}/proofread")
async def run_proofread(doc_id: str):
    doc = repository.get_document(doc_id)
    if not doc:
        raise HTTPException(404)
    paragraphs = repository.get_paragraphs(doc_id)
    rules = repository.list_rules()

    def on_progress(stage: str, done: int, total: int, new_in_step):
        push_ws(doc_id, {
            "type": "proofread_progress",
            "stage": stage, "done": done, "total": total,
            "new_in_step": len(new_in_step) if new_in_step else 0,
        })

    loop = asyncio.get_event_loop()
    fn = partial(proofreader.proofread, doc_id, paragraphs, rules, on_progress)
    errors = await loop.run_in_executor(None, fn)
    repository.insert_errors(errors)
    push_ws(doc_id, {"type": "proofread_done", "new": len(errors)})

    # 异步推荐
    asyncio.create_task(_push_recommendations(doc_id))

    return {
        "new": len(errors),
        "by_layer": _count_by_layer(errors),
        "state": repository.state_summary(doc_id),
    }


async def _push_recommendations(doc_id: str):
    try:
        all_errors = repository.list_errors(doc_id)
        recs = await recommendations.arecommend(all_errors)
        if recs:
            text = recommendations.format_for_chat(recs)
            push_ws(doc_id, {"type": "assistant_message", "text": text})
            repository.insert_chat_message(doc_id, "assistant", text, {"kind": "recommendation"})
    except Exception:
        pass


def _count_by_layer(errors):
    out = {}
    for e in errors:
        out[e.layer.value] = out.get(e.layer.value, 0) + 1
    return out


# ============ errors ============
@router.get("/documents/{doc_id}/errors")
async def list_errors(doc_id: str):
    if not repository.get_document(doc_id):
        raise HTTPException(404)
    return [e.model_dump() for e in repository.list_errors(doc_id)]


@router.post("/errors/{error_id}/accept")
async def accept_error(error_id: str, payload: dict = Body(default={})):
    err = repository.get_error(error_id)
    if not err:
        raise HTTPException(404)
    final_text = payload.get("final_text")
    status, msg = document_adapter.apply_revision(err.doc_id, err, final_text)
    repository.update_error_status(error_id, status, final_text=final_text or "")

    # L5 同步快检
    l5_warnings = []
    if status in (ReviewStatus.accepted, ReviewStatus.edited):
        before, after = document_adapter.get_paragraph_accepted_text(err.doc_id, err.paragraph_idx)
        l5_warnings = proofreader.l5_quick_check(err.doc_id, err.paragraph_idx,
                                                  err.original, final_text or err.suggestion)
        if l5_warnings:
            repository.insert_errors(l5_warnings)
        elif config.USE_LLM and config.ENABLE_L5_AI:
            # 后台 LLM 复核
            asyncio.create_task(_l5_ai_followup(err.doc_id, err.paragraph_idx, before, after))

    return {
        "msg": msg, "status": status.value,
        "l5_warnings": len(l5_warnings),
        "state": repository.state_summary(err.doc_id),
    }


async def _l5_ai_followup(doc_id: str, paragraph_idx: int, before: str, after: str):
    try:
        warnings = await proofreader.l5_ai_check(doc_id, paragraph_idx, before, after)
        if warnings:
            repository.insert_errors(warnings)
            push_ws(doc_id, {"type": "l5_warning", "count": len(warnings),
                             "paragraph_idx": paragraph_idx})
    except Exception:
        pass


@router.post("/errors/{error_id}/reject")
async def reject_error(error_id: str, payload: dict = Body(default={})):
    err = repository.get_error(error_id)
    if not err:
        raise HTTPException(404)
    reason = payload.get("reason", "")
    repository.update_error_status(error_id, ReviewStatus.rejected, user_feedback=reason)
    # 入 rule_candidate 草案
    if reason.strip():
        repository.insert_rule_candidate(
            summary=f"针对'{err.original[:20]}'类:{reason[:60]}",
            category=err.layer.value if err.layer.value in ("L1", "L2", "L3") else "custom",
            source="rejection",
            evidence=[err.original, reason],
        )
    return {"msg": "已拒绝", "state": repository.state_summary(err.doc_id)}


@router.post("/errors/{error_id}/undo")
async def undo_error(error_id: str):
    err = repository.get_error(error_id)
    if not err:
        raise HTTPException(404)
    repository.update_error_status(error_id, ReviewStatus.pending)
    # 重建工作 docx
    doc = repository.get_document(err.doc_id)
    if doc:
        all_errors = repository.list_errors(err.doc_id)
        document_adapter.rebuild_work_docx_from_errors(
            err.doc_id, doc.file_path,
            repository.get_document_work_path(err.doc_id),
            all_errors,
        )
    return {"msg": "已撤销", "state": repository.state_summary(err.doc_id)}


@router.post("/documents/{doc_id}/batch_accept")
async def batch_accept(doc_id: str, payload: dict = Body(default={})):
    confidence = payload.get("confidence")
    layer = payload.get("layer")
    errors = repository.list_errors(doc_id)
    applied = 0
    for err in errors:
        if err.status != ReviewStatus.pending:
            continue
        if confidence and err.confidence.value != confidence:
            continue
        if layer and err.layer.value != layer:
            continue
        status, _ = document_adapter.apply_revision(doc_id, err)
        repository.update_error_status(err.id, status)
        if status in (ReviewStatus.accepted, ReviewStatus.edited):
            applied += 1
    return {"applied": applied, "state": repository.state_summary(doc_id)}


@router.post("/documents/{doc_id}/batch_reject")
async def batch_reject(doc_id: str, payload: dict = Body(default={})):
    layer = payload.get("layer")
    reason = payload.get("reason", "")
    errors = repository.list_errors(doc_id)
    cnt = 0
    for err in errors:
        if err.status != ReviewStatus.pending:
            continue
        if layer and err.layer.value != layer:
            continue
        repository.update_error_status(err.id, ReviewStatus.rejected, user_feedback=reason)
        cnt += 1
    return {"rejected": cnt, "state": repository.state_summary(doc_id)}


# ============ 直接修改(选中文字立即应用) ============
@router.post("/documents/{doc_id}/direct_change")
async def direct_change(doc_id: str, payload: dict = Body(...)):
    paragraph_idx = payload.get("paragraph_idx")
    selected_text = (payload.get("selected_text") or "").strip("\r\n")
    new_text = payload.get("new_text", "")
    note = payload.get("note", "")
    if not selected_text:
        raise HTTPException(400, "selected_text 不能为空")

    paragraphs = repository.get_paragraphs(doc_id)
    if paragraph_idx >= len(paragraphs):
        raise HTTPException(400, "段落索引无效")
    text = paragraphs[paragraph_idx].text
    pos = text.find(selected_text)
    if pos < 0:
        raise HTTPException(400, f"段 {paragraph_idx} 找不到 '{selected_text[:30]}'")

    err = ProofreadError(
        id=uuid.uuid4().hex[:12], doc_id=doc_id,
        layer=Layer.USER, type="用户直接修改",
        confidence=Confidence.high,
        paragraph_idx=paragraph_idx,
        char_start=pos, char_end=pos + len(selected_text),
        original=selected_text, suggestion=new_text,
        explanation=note or "用户直接修改",
        source=FindingSource.user_direct,
    )
    repository.insert_errors([err])
    status, msg = document_adapter.apply_revision(doc_id, err, new_text)
    repository.update_error_status(err.id, status, final_text=new_text)
    return {"msg": msg, "finding_id": err.id, "state": repository.state_summary(doc_id)}


# ============ 候选改法 ============
@router.post("/documents/{doc_id}/suggest_alternatives")
async def suggest_alternatives(doc_id: str, payload: dict = Body(...)):
    paragraph_idx = payload.get("paragraph_idx")
    selected_text = (payload.get("selected_text") or "").strip()
    if not selected_text:
        raise HTTPException(400, "selected_text 不能为空")
    paragraphs = repository.get_paragraphs(doc_id)
    if paragraph_idx >= len(paragraphs):
        raise HTTPException(400, "段落索引无效")

    sys_prompt = """你是图书编辑助手。用户选中了一段文字,请给 3 个改写候选,保守→润色→重写。
输出 JSON 数组:[{"text":"...","label":"保守|润色|重写","reason":"15字内"}]"""
    user = (
        f"段落原文:\n{paragraphs[paragraph_idx].text}\n\n"
        f"选中:\n{selected_text}\n\n输出 JSON 数组。"
    )
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: llm.chat_json(sys_prompt, user, max_tokens=800))
    except Exception as e:
        raise HTTPException(500, f"LLM 失败:{e}")
    return {"alternatives": result[:3] if isinstance(result, list) else []}


# ============ 导出(导出前 L5 阻断) ============
@router.post("/documents/{doc_id}/export")
async def export(doc_id: str):
    errors = repository.list_errors(doc_id)
    # 跑一次 L5 快检阻断
    pending_l5 = [e for e in errors if e.layer == Layer.L5 and e.status == ReviewStatus.pending]
    if pending_l5:
        raise HTTPException(400, f"还有 {len(pending_l5)} 条 L5 修订风险待处理,请先 review 再导出")
    work_path = repository.get_document_work_path(doc_id)
    if not work_path:
        raise HTTPException(404)
    return {"download_url": f"/api/documents/{doc_id}/download"}


# ============ chat ============
@router.get("/documents/{doc_id}/messages")
async def get_messages(doc_id: str):
    return [m.model_dump() for m in repository.list_chat_messages(doc_id)]


@router.post("/documents/{doc_id}/chat")
async def chat(doc_id: str, payload: dict = Body(...)):
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message 不能为空")
    paragraphs = repository.get_paragraphs(doc_id)
    rules = repository.list_rules()
    history = repository.list_chat_messages(doc_id, limit=20)

    result = await chat_agent.respond(doc_id, message, paragraphs, rules, history)
    if result["new_edits"]:
        repository.insert_errors(result["new_edits"])
    candidates = []
    for c in result["new_candidates"]:
        cand = repository.insert_rule_candidate(**c)
        candidates.append(cand.model_dump())
    return {
        "reply": result["reply"],
        "new_edits": len(result["new_edits"]),
        "new_candidates": candidates,
        "state": repository.state_summary(doc_id),
    }


# ============ rules ============
@router.get("/rules")
async def list_user_rules():
    return [r.model_dump() for r in repository.list_rules()]


@router.delete("/rules/{rule_id}")
async def disable_rule(rule_id: str):
    ok = repository.disable_rule(rule_id)
    return {"ok": ok}


@router.get("/rule_candidates")
async def list_candidates(status: str = "draft"):
    return [c.model_dump() for c in repository.list_rule_candidates(status)]


@router.post("/rule_candidates/{cid}/approve")
async def approve(cid: str):
    rule = repository.approve_rule_candidate(cid)
    if not rule:
        raise HTTPException(404)
    return {"rule": rule.model_dump()}


@router.post("/rule_candidates/{cid}/archive")
async def archive(cid: str):
    ok = repository.archive_rule_candidate(cid)
    return {"ok": ok}


# ============ skills ============
@router.get("/skills")
async def get_skills():
    # 序列化时去掉 runner(callable 不能 JSON)
    out = []
    for s in list_skills():
        d = s.model_dump(exclude={"runner"})
        d["runnable"] = s.runner is not None
        out.append(d)
    return out


@router.patch("/skills/{skill_id}")
async def patch_skill(skill_id: str, payload: dict = Body(...)):
    enabled = bool(payload.get("enabled", True))
    # user skill 走 user_skills 表
    if skill_id.startswith("user."):
        uid = skill_id[5:]
        row = user_skills.update_user_skill(uid, enabled=1 if enabled else 0)
        if not row:
            raise HTTPException(404)
        return {"ok": True, "skill_id": skill_id, "enabled": enabled}
    ok = skill_registry.set_enabled(skill_id, enabled)
    if not ok:
        raise HTTPException(404, "skill 不存在")
    return {"ok": True, "skill_id": skill_id, "enabled": enabled}


# ---- user-defined prompt skills ----
@router.post("/user_skills")
async def create_user_skill_api(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    prompt = (payload.get("prompt") or "").strip()
    if not name or not prompt:
        raise HTTPException(400, "name 和 prompt 必填")
    row = user_skills.create_user_skill(
        name=name,
        description=payload.get("description", ""),
        prompt=prompt,
        phase=int(payload.get("phase", 50)),
    )
    return row


@router.put("/user_skills/{uid}")
async def update_user_skill_api(uid: str, payload: dict = Body(...)):
    row = user_skills.update_user_skill(uid, **payload)
    if not row:
        raise HTTPException(404)
    return row


@router.delete("/user_skills/{uid}")
async def delete_user_skill_api(uid: str):
    ok = user_skills.delete_user_skill(uid)
    return {"ok": ok}


@router.get("/user_skills/{uid}")
async def get_user_skill_api(uid: str):
    row = user_skills.get_user_skill(uid)
    if not row:
        raise HTTPException(404)
    return row


# ============ settings(LLM 配置) ============
@router.get("/settings")
async def get_settings_api():
    from ..services import settings_store
    return settings_store.get_masked()


@router.put("/settings")
async def update_settings_api(payload: dict = Body(...)):
    from ..services import settings_store
    new = settings_store.update_settings(payload)
    # 返回脱敏版
    return settings_store.get_masked()


@router.post("/settings/test")
async def test_settings_api(payload: dict = Body(default={})):
    """测试连接,**不写入 DB**。用显式参数构造临时 client。"""
    cur = settings_store.get_settings()
    # 合并:payload 优先,未传的用当前 DB 值
    provider = payload.get("LLM_PROVIDER", cur["LLM_PROVIDER"])
    base_url = payload.get("OPENAI_BASE_URL", cur["OPENAI_BASE_URL"])
    api_key = payload.get("OPENAI_API_KEY") or cur["OPENAI_API_KEY"]
    model = payload.get("LLM_MODEL", cur["LLM_MODEL"])

    diag = {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key_prefix": api_key[:8] + "..." if len(api_key) > 8 else "(空)",
    }

    if not api_key:
        return {"ok": False, "error": "API Key 必填", "diag": diag}

    try:
        msg = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: llm.chat_explicit(
                provider, base_url, api_key, model,
                [{"role": "user", "content": "回复一个字"}],
                max_tokens=20,
            ),
        )
        return {
            "ok": True, "model": model, "diag": diag,
            "reply": (msg.content or "(空回复)")[:100],
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "diag": diag}




# ============ WebSocket(进度推送) ============
@router.websocket("/ws/{doc_id}")
async def ws_endpoint(websocket: WebSocket, doc_id: str):
    global MAIN_LOOP
    await websocket.accept()
    if not repository.get_document(doc_id):
        await websocket.send_json({"type": "error", "msg": "文档不存在"})
        await websocket.close()
        return
    if MAIN_LOOP is None:
        MAIN_LOOP = asyncio.get_event_loop()
    WS_CONNECTIONS[doc_id] = websocket
    try:
        await websocket.send_json({"type": "ws_open"})
        while True:
            await websocket.receive_text()  # 客户端 ping,无业务
    except WebSocketDisconnect:
        pass
    finally:
        WS_CONNECTIONS.pop(doc_id, None)
