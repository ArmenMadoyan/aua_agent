"""
Route each user turn to the right specialist (or a plain LLM) and run it.

- general: no tools — greetings, generic Q&A, tasks outside AUA policy + course files
- kb: AUA policy RAG agent
- course: slides / PDF assessments agent (optional syllabus injected into last user turn)
- grading: vision model — score/evaluate student work (routed by intent, not by attachments alone)

Streaming: use ``iter_chat_turn_tokens`` with ``st.write_stream``; ``run_chat_turn`` consumes the same iterator.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ai.agents import course_agent, kb_agent
from ai.chat_context import messages_for_llm_turn
from ai.config import API_KEY, GRADING_VISION_MODEL
from ai.grading import build_grading_lc_messages

RouterChoice = Literal["general", "kb", "course", "grading"]
ForceAgent = Literal["auto", "general", "kb", "course", "grading"]

_AGENT_CONTEXT: dict[str, str] = {"user_role": "expert"}


class _RouteDecision(BaseModel):
    agent: RouterChoice = Field(
        description=(
            "general: small talk, unrelated topics, or generic help with no AUA policy lookup "
            "and no request for slides/quizzes/exams/PDF/PPTX and no grading of student work. "
            "kb: AUA / university policies, procedures, official AUA information. "
            "course: create/generate/make teaching FILES — slides, homework, quiz, midterm, final exam, "
            "PPTX, or PDF assessments. Use course even when the user attached PDFs or scans "
            "(e.g. syllabus + old homework) if the latest request is to PRODUCE new materials. "
            "grading: primary ask is to SCORE/GRADE/EVALUATE student work with a rubric or feedback "
            "on a submission—not to author a new exam file for future students."
        )
    )


_router_llm = ChatOpenAI(
    model_name="gpt-4.1",
    openai_api_key=API_KEY,
    temperature=0,
).with_structured_output(_RouteDecision)

_general_llm = ChatOpenAI(
    model_name="gpt-4.1",
    openai_api_key=API_KEY,
    temperature=0.2,
)

_grading_llm = ChatOpenAI(
    model_name=GRADING_VISION_MODEL,
    openai_api_key=API_KEY,
    temperature=0.2,
)

_GENERAL_SYSTEM = (
    "You are a helpful assistant for a university operations app. "
    "Answer directly and concisely. You do not search AUA policy PDFs or generate "
    "course files. If the user clearly needs official AUA policy text, say the policy "
    "assistant can search the documents. If they need slides or written assessments "
    "as files, say the course-materials assistant can build those."
)


def _format_transcript(messages: Sequence[dict], *, max_messages: int = 12) -> str:
    lines: list[str] = []
    for m in messages[-max_messages:]:
        role = m.get("role", "")
        raw = m.get("content")
        if isinstance(raw, list):
            text = "[multimodal message]"
        else:
            text = (raw or "")[:4000]
        if m.get("attachments"):
            n = len(m["attachments"])
            text = f"{text} [+{n} image(s)/page(s) attached — may be syllabus, rubric, or student work]"
        lines.append(f"{role.upper()}: {text}")
    return "\n".join(lines) if lines else "(empty)"


def _strip_for_text_agents(messages: list[dict]) -> list[dict]:
    """LangGraph text agents must not receive ``attachments`` on message dicts."""
    out: list[dict] = []
    for m in messages:
        c = m.get("model_content")
        if c is None:
            c = m.get("content")
        if not isinstance(c, str):
            c = str(c) if c is not None else ""
        out.append({"role": m.get("role"), "content": c})
    return out


def _route_agent(
    messages: Sequence[dict],
    *,
    syllabus_available: bool,
) -> RouterChoice:
    syllabus_note = (
        "\nNote: A syllabus is loaded in the UI for this session (use `course` if they "
        "want materials that should follow that syllabus).\n"
        if syllabus_available
        else ""
    )
    prompt = (
        "Choose exactly one handler for the latest user need. Consider the full thread.\n"
        f"{syllabus_note}\n"
        "---\n"
        f"{_format_transcript(messages)}\n"
        "---"
    )
    decision = _router_llm.invoke(
        [
            SystemMessage(
                content=(
                    "You only route: respond with structured output. "
                    "Prefer `kb` when AUA/university policy or official school info is central. "
                    "Prefer `course` when they want to CREATE deliverable teaching files: slides, "
                    "homework, quiz, midterm, final exam, PPTX, PDF assessments—even if they attached "
                    "multiple PDFs or images (syllabus, old homework, rubric). The latest user "
                    "instruction wins: 'make/generate/build a final exam' → course, not grading. "
                    "Prefer `grading` only when the main request is to grade/score/evaluate student "
                    "submissions or give feedback on turned-in work (often with a rubric). "
                    "Attachments alone do not imply grading. Use `general` otherwise."
                )
            ),
            HumanMessage(content=prompt),
        ]
    )
    return decision.agent


def _inject_syllabus(messages: list[dict], syllabus: str) -> list[dict]:
    out = [dict(m) for m in messages]
    if not syllabus.strip() or not out or out[-1].get("role") != "user":
        return out
    user_ask = out[-1]["content"]
    out[-1] = {
        "role": "user",
        "content": (
            "The instructor uploaded the following syllabus. Use it for this request "
            "(and infer weeks/units from it when the user refers to them).\n\n"
            "--- SYLLABUS START ---\n"
            f"{syllabus.strip()}\n"
            "--- SYLLABUS END ---\n\n"
            f"Instructor request:\n{user_ask}"
        ),
    }
    return out


def _general_lc_messages(messages: list[dict]) -> list:
    lc: list = [SystemMessage(content=_GENERAL_SYSTEM)]
    for m in messages:
        if m.get("role") == "user":
            c = m.get("content")
            if not isinstance(c, str):
                c = str(c) if c is not None else ""
            lc.append(HumanMessage(content=c))
        elif m.get("role") == "assistant":
            lc.append(AIMessage(content=m.get("content") or ""))
    return lc


def _stream_grading_llm(messages: list[dict]) -> Iterator[str]:
    lc = build_grading_lc_messages(messages)
    for chunk in _grading_llm.stream(lc):
        if getattr(chunk, "content", None):
            yield chunk.content


def _collect_tool_names_from_updates(payload: dict[str, Any], acc: list[str]) -> None:
    for _node, inner in payload.items():
        if not isinstance(inner, dict):
            continue
        for m in inner.get("messages", []):
            for tc in getattr(m, "tool_calls", None) or []:
                n = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if n:
                    acc.append(n)


def _stream_langgraph_agent(agent, messages: list[dict], tool_acc: list[str]) -> Iterator[str]:
    for chunk in agent.stream(
        {"messages": messages},
        context=_AGENT_CONTEXT,
        stream_mode=["messages", "updates"],
    ):
        mode, payload = chunk[0], chunk[1]
        if mode == "messages":
            msg, meta = payload
            if meta.get("langgraph_node") != "model":
                continue
            c = getattr(msg, "content", None) or ""
            if c:
                yield c
        elif mode == "updates" and isinstance(payload, dict):
            _collect_tool_names_from_updates(payload, tool_acc)


@dataclass
class OrchestratorResult:
    reply: str
    agent_used: RouterChoice
    tool_names: list[str]


def iter_chat_turn_tokens(
    messages: list[dict],
    *,
    syllabus_text: str | None = None,
    force_agent: ForceAgent = "auto",
    meta: dict | None = None,
) -> Iterator[str]:
    """
    Yield text chunks for the assistant reply. Pass ``meta`` as ``{}`` to receive
    ``meta['agent_used']`` and ``meta['tool_names']`` after the iterator finishes.
    """
    if meta is None:
        meta = {}
    tool_acc: list[str] = []
    meta["agent_used"] = ""
    meta["tool_names"] = []

    syllabus = (syllabus_text or "").strip()
    syllabus_available = bool(syllabus)

    # Drop stale file payloads from earlier turns (vision + long extracts).
    msgs = messages_for_llm_turn([dict(m) for m in messages])

    try:
        if force_agent == "general":
            meta["agent_used"] = "general"
            trimmed = _strip_for_text_agents(msgs)
            for chunk in _general_llm.stream(_general_lc_messages(trimmed)):
                if getattr(chunk, "content", None):
                    yield chunk.content
            return

        if force_agent == "kb":
            meta["agent_used"] = "kb"
            yield from _stream_langgraph_agent(kb_agent, _strip_for_text_agents(msgs), tool_acc)
            return

        if force_agent == "course":
            meta["agent_used"] = "course"
            base = _strip_for_text_agents(msgs)
            to_send = _inject_syllabus(base, syllabus) if syllabus_available else base
            yield from _stream_langgraph_agent(course_agent, to_send, tool_acc)
            return

        if force_agent == "grading":
            meta["agent_used"] = "grading"
            yield from _stream_grading_llm(msgs)
            return

        choice = _route_agent(msgs, syllabus_available=syllabus_available)
        meta["agent_used"] = choice

        if choice == "general":
            trimmed = _strip_for_text_agents(msgs)
            for chunk in _general_llm.stream(_general_lc_messages(trimmed)):
                if getattr(chunk, "content", None):
                    yield chunk.content
            return

        if choice == "kb":
            yield from _stream_langgraph_agent(kb_agent, _strip_for_text_agents(msgs), tool_acc)
            return

        if choice == "grading":
            yield from _stream_grading_llm(msgs)
            return

        base = _strip_for_text_agents(msgs)
        to_send = _inject_syllabus(base, syllabus) if syllabus_available else base
        yield from _stream_langgraph_agent(course_agent, to_send, tool_acc)
    finally:
        meta["tool_names"] = list(dict.fromkeys(tool_acc))


def run_chat_turn(
    messages: list[dict],
    *,
    syllabus_text: str | None = None,
    force_agent: ForceAgent = "auto",
) -> OrchestratorResult:
    """
    Run one assistant turn (buffered). Same routing as ``iter_chat_turn_tokens``.
    """
    meta: dict = {}
    parts: list[str] = []
    for piece in iter_chat_turn_tokens(
        messages,
        syllabus_text=syllabus_text,
        force_agent=force_agent,
        meta=meta,
    ):
        parts.append(piece)
    return OrchestratorResult(
        reply="".join(parts),
        agent_used=meta["agent_used"],
        tool_names=meta.get("tool_names", []),
    )
