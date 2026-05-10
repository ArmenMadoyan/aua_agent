from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.document_text import merge_reference_block_into_last_user
from backend.ai.orchestrator import OrchestratorResult, iter_chat_turn_tokens, run_chat_turn

_SENTINEL = object()


async def _sync_gen_to_async(sync_gen: Iterator[str]) -> AsyncIterator[str]:
    """Bridge a blocking sync generator to an async iterator via a thread + queue."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _produce():
        try:
            for item in sync_gen:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    loop.run_in_executor(None, _produce)

    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        if isinstance(item, Exception):
            raise item
        yield item
from backend.ai.vector_store import (
    add_document as vs_add_document,
    delete_document as vs_delete_document,
    document_exists as vs_document_exists,
    list_documents as vs_list_documents,
)
from backend.config import DEFAULT_USER_ID
from backend.models import Conversation, LLMModel, Message


# ── helpers ──────────────────────────────────────────────────────────────────


async def _default_llm_model_id(session: AsyncSession) -> int | None:
    result = await session.execute(
        select(LLMModel.id)
        .where(LLMModel.is_default.is_(True))
        .order_by(LLMModel.display_order, LLMModel.id)
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return int(row) if row is not None else None


def _ts_str(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ── Chat services ────────────────────────────────────────────────────────────


async def create_session(
    session: AsyncSession,
    user_id: int | None = None,
    title: str | None = None,
) -> int:
    uid = DEFAULT_USER_ID if user_id is None else user_id
    conv = Conversation(user_id=uid, title=title)
    session.add(conv)
    await session.flush()
    await session.commit()
    return conv.id


async def list_sessions(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "created_at": _ts_str(r.created_at),
            "title": r.title,
        }
        for r in rows
    ]


async def session_exists(session: AsyncSession, chat_id: int) -> bool:
    result = await session.execute(
        select(Conversation.id).where(Conversation.id == chat_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_messages(session: AsyncSession, chat_id: int) -> list[dict]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == chat_id)
        .order_by(Message.id.asc())
    )
    rows = result.scalars().all()
    return [{"role": r.role, "content": r.content} for r in rows]


async def add_message(
    session: AsyncSession,
    chat_id: int,
    role: str,
    content: str,
    *,
    agent_name: str | None = None,
    agent_id: str | None = None,
    llm_model_id: int | None = None,
    tools_called: list[str] | None = None,
) -> None:
    model_id = llm_model_id
    if role == "assistant" and model_id is None:
        model_id = await _default_llm_model_id(session)

    msg = Message(
        conversation_id=chat_id,
        role=role,
        content=content,
        agent_name=agent_name,
        agent_id=agent_id,
        llm_model_id=model_id,
        tools_called=tools_called,
    )
    session.add(msg)

    await session.execute(
        update(Conversation)
        .where(Conversation.id == chat_id)
        .values(updated_at=func.now())
    )
    await session.commit()


async def delete_chat(session: AsyncSession, chat_id: int) -> bool:
    result = await session.execute(
        delete(Conversation).where(Conversation.id == chat_id).returning(Conversation.id)
    )
    await session.commit()
    return result.scalar_one_or_none() is not None


async def answer_question(
    session: AsyncSession,
    chat_id: int,
    question: str,
    *,
    agent: str = "auto",
    syllabus_text: str | None = None,
    attachments: list[dict] | None = None,
    reference_documents: list[tuple[str, str]] | None = None,
) -> dict:
    history = await get_messages(session, chat_id)

    user_turn: dict = {"role": "user", "content": question}
    if attachments:
        user_turn["attachments"] = attachments

    messages = history + [user_turn]
    if reference_documents and (attachments or agent == "grading"):
        messages = merge_reference_block_into_last_user(
            messages, reference_parts=reference_documents
        )

    out: OrchestratorResult = await asyncio.to_thread(
        run_chat_turn,
        messages,
        chat_id=chat_id,
        syllabus_text=syllabus_text,
        force_agent=agent,
    )

    agent_label = out.agent_used
    tools = out.tool_names
    llm_id = await _default_llm_model_id(session)

    persist_question = question
    prefixes: list[str] = []
    if attachments:
        prefixes.append(
            f"[Homework: {len(attachments)} image(s)/page(s) — binary not stored in history]"
        )
    if reference_documents:
        prefixes.append(
            f"[Reference docs: {len(reference_documents)} — full text not stored in history]"
        )
    if prefixes:
        persist_question = "\n".join(prefixes) + "\n\n" + question

    await add_message(session, chat_id, "user", persist_question, agent_name=agent_label)
    await add_message(
        session,
        chat_id,
        "assistant",
        out.reply,
        agent_name=agent_label,
        llm_model_id=llm_id,
        tools_called=tools or None,
    )

    return {
        "chat_id": chat_id,
        "question": question,
        "answer": out.reply,
        "agent_used": agent_label,
    }


async def stream_answer(
    session: AsyncSession,
    chat_id: int,
    question: str,
    *,
    agent: str = "auto",
    syllabus_text: str | None = None,
    attachments: list[dict] | None = None,
    reference_documents: list[tuple[str, str]] | None = None,
):
    """Async generator that yields token strings for SSE streaming."""
    history = await get_messages(session, chat_id)

    user_turn: dict = {"role": "user", "content": question}
    if attachments:
        user_turn["attachments"] = attachments

    messages = history + [user_turn]
    if reference_documents and (attachments or agent == "grading"):
        messages = merge_reference_block_into_last_user(
            messages, reference_parts=reference_documents
        )

    meta: dict = {}
    collected: list[str] = []

    sync_gen = iter_chat_turn_tokens(
        messages,
        chat_id=chat_id,
        syllabus_text=syllabus_text,
        force_agent=agent,
        meta=meta,
    )

    async for token in _sync_gen_to_async(sync_gen):
        collected.append(token)
        yield token

    full_reply = "".join(collected)
    agent_label = meta.get("agent_used", "general")
    tools = meta.get("tool_names", [])
    llm_id = await _default_llm_model_id(session)

    persist_question = question
    prefixes: list[str] = []
    if attachments:
        prefixes.append(
            f"[Homework: {len(attachments)} image(s)/page(s) — binary not stored in history]"
        )
    if reference_documents:
        prefixes.append(
            f"[Reference docs: {len(reference_documents)} — full text not stored in history]"
        )
    if prefixes:
        persist_question = "\n".join(prefixes) + "\n\n" + question

    await add_message(session, chat_id, "user", persist_question, agent_name=agent_label)
    await add_message(
        session,
        chat_id,
        "assistant",
        full_reply,
        agent_name=agent_label,
        llm_model_id=llm_id,
        tools_called=tools or None,
    )


# ── Knowledge services ───────────────────────────────────────────────────────


async def list_knowledge_documents() -> list[str]:
    return vs_list_documents()


async def knowledge_add_document(content: str, file_name: str | None = None) -> dict:
    doc_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    is_duplicate = vs_document_exists(doc_hash)
    vs_add_document(content, file_name=file_name)
    return {"success": True, "doc_hash": doc_hash, "is_duplicate": is_duplicate}


async def knowledge_upload_document(content_str: str, file_name: str | None = None) -> dict:
    doc_hash = hashlib.md5(content_str.encode("utf-8")).hexdigest()
    is_duplicate = vs_document_exists(doc_hash)
    vs_add_document(content_str, file_name=file_name)
    return {"success": True, "doc_hash": doc_hash, "is_duplicate": is_duplicate}


async def knowledge_delete_document(doc_hash: str) -> bool:
    return vs_delete_document(doc_hash)
