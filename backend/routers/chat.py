from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from ai.document_text import merge_reference_block_into_last_user
from ai.orchestrator import run_chat_turn
from backend.db import (
    add_message,
    delete_session,
    get_default_llm_model_id,
    get_messages,
    list_sessions,
    session_exists,
)


chat_router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    chat_id: int


class HomeworkAttachment(BaseModel):
    mime_type: str = Field(..., description="e.g. image/jpeg, image/png")
    base64: str = Field(..., description="Standard base64 of file bytes or rasterized PDF page PNG")


class ReferenceDocumentPayload(BaseModel):
    title: str = Field(default="document", max_length=256)
    text: str = Field(..., max_length=120_000)


class ChatQuestionRequest(BaseModel):
    chat_id: int
    question: str
    agent: Literal["auto", "general", "kb", "course", "grading"] = Field(
        default="auto",
        description="auto: router picks agent. Otherwise force that mode. Use grading for rubric + submission.",
    )
    syllabus_text: str | None = Field(
        default=None,
        description="Optional syllabus for course tasks (when agent is course or router chooses course).",
    )
    attachments: list[HomeworkAttachment] | None = Field(
        default=None,
        description="Optional images (or PDF pages as PNG) for the homework grading agent.",
    )
    reference_documents: list[ReferenceDocumentPayload] | None = Field(
        default=None,
        description="Rubric or other reference text (multiple docs). Merged into the latest user turn.",
    )

    @model_validator(mode="after")
    def validate_reference_documents(self):
        if not self.reference_documents:
            return self
        if len(self.reference_documents) > 40:
            raise ValueError("At most 40 reference documents per request.")
        total = sum(len(d.text) for d in self.reference_documents)
        if total > 480_000:
            raise ValueError("Combined reference document text exceeds limit (480k characters).")
        return self

    @field_validator("attachments")
    @classmethod
    def cap_attachments(cls, v: list[HomeworkAttachment] | None) -> list[HomeworkAttachment] | None:
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("At most 20 attachment images/pages per request.")
        return v


@chat_router.get("/list")
def list_chat_sessions():
    return {"sessions": list_sessions()}


@chat_router.post("/get_messages")
def get_chat_messages(payload: ChatRequest):
    if not session_exists(payload.chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"chat_id": payload.chat_id, "messages": get_messages(payload.chat_id)}


@chat_router.post("/answer")
def answer_chat_question(payload: ChatQuestionRequest):
    history = get_messages(payload.chat_id)

    user_turn: dict = {"role": "user", "content": payload.question}
    if payload.attachments:
        user_turn["attachments"] = [
            {"mime_type": a.mime_type, "base64": a.base64} for a in payload.attachments
        ]

    messages = history + [user_turn]
    if payload.reference_documents and (
        payload.attachments or payload.agent == "grading"
    ):
        ref_parts = [(d.title, d.text) for d in payload.reference_documents]
        messages = merge_reference_block_into_last_user(messages, reference_parts=ref_parts)

    try:
        out = run_chat_turn(
            messages,
            syllabus_text=payload.syllabus_text,
            force_agent=payload.agent,
        )
        reply = out.reply
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    agent_label = out.agent_used
    tools = out.tool_names
    llm_id = get_default_llm_model_id()

    persist_question = payload.question
    prefixes: list[str] = []
    if payload.attachments:
        prefixes.append(
            f"[Homework: {len(payload.attachments)} image(s)/page(s) — binary not stored in history]"
        )
    if payload.reference_documents:
        prefixes.append(
            f"[Reference docs: {len(payload.reference_documents)} — full text not stored in history]"
        )
    if prefixes:
        persist_question = "\n".join(prefixes) + "\n\n" + payload.question

    add_message(
        payload.chat_id,
        "user",
        persist_question,
        agent_name=agent_label,
    )
    add_message(
        payload.chat_id,
        "assistant",
        reply,
        agent_name=agent_label,
        llm_model_id=llm_id,
        tools_called=tools or None,
    )

    return {
        "chat_id": payload.chat_id,
        "question": payload.question,
        "answer": reply,
        "agent_used": agent_label,
    }


@chat_router.delete("/delete", status_code=204)
def delete_chat(chat_id: int):
    messages = get_messages(chat_id)
    if not messages and not session_exists(chat_id):
        raise HTTPException(
            status_code=404,
            detail=f"Chat with ID {chat_id} not found. Use GET /chat/list to see available sessions."
        )

    delete_session(chat_id)

    return None
