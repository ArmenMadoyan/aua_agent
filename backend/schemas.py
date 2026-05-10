from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.validators import validate_attachment_count, validate_reference_documents


# ── Chat ─────────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    chat_id: int


class HomeworkAttachment(BaseModel):
    mime_type: str = Field(..., description="e.g. image/jpeg, image/png")
    base64: str = Field(
        ..., description="Standard base64 of file bytes or rasterized PDF page PNG"
    )


class ReferenceDocumentPayload(BaseModel):
    title: str = Field(default="document", max_length=256)
    text: str = Field(..., max_length=120_000)


class ChatQuestionRequest(BaseModel):
    chat_id: int
    question: str
    agent: Literal["auto", "general", "kb", "course", "grading"] = Field(
        default="auto",
        description="auto: router picks agent. Otherwise force that mode.",
    )
    syllabus_text: str | None = Field(
        default=None,
        description="Optional syllabus for course tasks.",
    )
    attachments: list[HomeworkAttachment] | None = Field(
        default=None,
        description="Optional images (or PDF pages as PNG) for the grading agent.",
    )
    reference_documents: list[ReferenceDocumentPayload] | None = Field(
        default=None,
        description="Rubric or other reference text. Merged into the latest user turn.",
    )

    @field_validator("attachments")
    @classmethod
    def cap_attachments(
        cls, v: list[HomeworkAttachment] | None
    ) -> list[HomeworkAttachment] | None:
        return validate_attachment_count(v)

    @model_validator(mode="after")
    def cap_reference_documents(self):
        validate_reference_documents(self.reference_documents)
        return self


class CreateSessionRequest(BaseModel):
    user_id: int | None = None
    title: str | None = None


class CreateSessionResponse(BaseModel):
    chat_id: int


class ChatAnswerResponse(BaseModel):
    chat_id: int
    question: str
    answer: str
    agent_used: str


class MessageOut(BaseModel):
    role: str
    content: str


class ChatMessagesResponse(BaseModel):
    chat_id: int
    messages: list[MessageOut]


class SessionOut(BaseModel):
    id: int
    created_at: str
    title: str | None


class ChatListResponse(BaseModel):
    sessions: list[SessionOut]


# ── Knowledge ────────────────────────────────────────────────────────────────


class AddDocumentRequest(BaseModel):
    content: str
    file_name: str | None = None


class DeleteDocumentRequest(BaseModel):
    doc_hash: str


class DocumentResponse(BaseModel):
    success: bool
    doc_hash: str
    is_duplicate: bool


class DocumentListResponse(BaseModel):
    documents: list[str]


class DeleteDocumentResponse(BaseModel):
    success: bool
    message: str
