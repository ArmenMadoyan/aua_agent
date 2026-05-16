from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from backend.auth import require_auth
from backend.db import get_session
from backend import schemas, services
from backend.app.upload_bundle import normalize_attachments

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


# ── Chat endpoints ───────────────────────────────────────────────────────────


@router.get("/chat/list", response_model=schemas.ChatListResponse)
async def list_chat_sessions(session: AsyncSession = Depends(get_session)):
    rows = await services.list_sessions(session)
    return {"sessions": rows}


@router.post("/chat/create", response_model=schemas.CreateSessionResponse)
async def create_chat_session(
    payload: schemas.CreateSessionRequest,
    session: AsyncSession = Depends(get_session),
):
    chat_id = await services.create_session(
        session, user_id=payload.user_id, title=payload.title
    )
    return {"chat_id": chat_id}


@router.post("/chat/get_messages", response_model=schemas.ChatMessagesResponse)
async def get_chat_messages(
    payload: schemas.ChatRequest,
    session: AsyncSession = Depends(get_session),
):
    if not await services.session_exists(session, payload.chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = await services.get_messages(session, payload.chat_id)
    return {"chat_id": payload.chat_id, "messages": messages}


@router.post("/chat/answer", response_model=schemas.ChatAnswerResponse)
async def answer_chat_question(
    payload: schemas.ChatQuestionRequest,
    session: AsyncSession = Depends(get_session),
):
    question = payload.question
    attachments = None
    if payload.attachments:
        raw = [
            {"mime_type": a.mime_type, "base64": a.base64} for a in payload.attachments
        ]
        question, processed = normalize_attachments(question, raw)
        attachments = processed or None

    ref_parts = None
    if payload.reference_documents:
        ref_parts = [(d.title, d.text) for d in payload.reference_documents]

    try:
        result = await services.answer_question(
            session,
            payload.chat_id,
            question,
            agent=payload.agent,
            syllabus_text=payload.syllabus_text,
            attachments=attachments,
            reference_documents=ref_parts,
        )
    except Exception as e:
        logger.exception("Error in /chat/answer: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.post("/chat/stream")
async def stream_chat_answer(
    payload: schemas.ChatQuestionRequest,
    session: AsyncSession = Depends(get_session),
):
    question = payload.question
    attachments = None
    if payload.attachments:
        raw = [
            {"mime_type": a.mime_type, "base64": a.base64} for a in payload.attachments
        ]
        question, processed = normalize_attachments(question, raw)
        attachments = processed or None

    ref_parts = None
    if payload.reference_documents:
        ref_parts = [(d.title, d.text) for d in payload.reference_documents]

    async def event_generator():
        try:
            async for token in services.stream_answer(
                session,
                payload.chat_id,
                question,
                agent=payload.agent,
                syllabus_text=payload.syllabus_text,
                attachments=attachments,
                reference_documents=ref_parts,
            ):
                yield {"data": json.dumps(token)}
        except Exception as e:
            logger.exception("Error in /chat/stream: %s", e)
            yield {"data": f"[ERROR] {e}"}

    return EventSourceResponse(event_generator())


@router.delete("/chat/delete", status_code=204)
async def delete_chat(
    chat_id: int,
    session: AsyncSession = Depends(get_session),
):
    exists = await services.session_exists(session, chat_id)
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Chat with ID {chat_id} not found.",
        )
    await services.delete_chat(session, chat_id)
    return None


# ── Knowledge endpoints ──────────────────────────────────────────────────────


@router.get("/knowledge/list", response_model=schemas.DocumentListResponse)
async def list_knowledge_documents():
    documents = await services.list_knowledge_documents()
    return {"documents": documents}


@router.post("/knowledge/add", response_model=schemas.DocumentResponse)
async def add_knowledge_document(payload: schemas.AddDocumentRequest):
    try:
        result = await services.knowledge_add_document(
            payload.content, file_name=payload.file_name
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding document: {e}")


@router.post("/knowledge/upload", response_model=schemas.DocumentResponse)
async def upload_knowledge_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        content_str = content.decode("utf-8")
        result = await services.knowledge_upload_document(
            content_str, file_name=file.filename
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading document: {e}")


@router.delete("/knowledge/delete", response_model=schemas.DeleteDocumentResponse)
async def delete_knowledge_document(payload: schemas.DeleteDocumentRequest):
    deleted = await services.knowledge_delete_document(payload.doc_hash)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Document with hash '{payload.doc_hash}' not found in knowledge base",
        )
    return {
        "success": True,
        "message": f"Document with hash '{payload.doc_hash}' deleted successfully",
    }
