"""
Route each user turn to the right specialist (or a plain LLM) and run it.

- general: no tools — greetings, generic Q&A, tasks outside AUA policy + course files
- kb: AUA policy RAG agent
- course: slides / PDF assessments agent (optional syllabus injected into last user turn)
- grading: vision model — score/evaluate student work (routed by intent, not by attachments alone)

Streaming: use ``iter_chat_turn_tokens`` with ``st.write_stream``; ``run_chat_turn`` consumes the same iterator.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from backend.app.agents.general_agent import GeneralAgent
from backend.app.agents.grading_agent import GradingAgent
from backend.app.agents.router_agent import RouterAgent, RouterChoice

logger = logging.getLogger(__name__)

ForceAgent = Literal["auto", "general", "kb", "course", "grading"]

# Lazy singletons — set by init_agents() at startup
_kb_agent_instance = None
_course_agent_instance = None


def init_agents(checkpointer=None) -> None:
    """Build KB and course agents. Called once during app lifespan."""
    global _kb_agent_instance, _course_agent_instance
    from backend.app.agents.kb_agent import KBAgent
    from backend.app.agents.course_agent import CourseAgent

    logger.info("Initializing KB and course agents")
    kb = KBAgent(checkpointer=checkpointer)
    kb.build()
    _kb_agent_instance = kb

    course = CourseAgent(checkpointer=checkpointer)
    course.build()
    _course_agent_instance = course
    logger.info("Agents initialized")


def _get_kb_agent():
    return _kb_agent_instance.get_agent()


def _get_course_agent():
    return _course_agent_instance.get_agent()


# ── message helpers ─────────────────────────────────────────────────


def _messages_for_llm_turn(messages: list[dict]) -> list[dict]:
    """
    Build the payload for one model call.

    Earlier user turns are reduced to their display ``content`` only (no ``attachments``,
    no ``model_content``), so homework scans and rubric dumps are not re-sent forever.
    Only the **last** message in the list may include vision images and full extracted text.
    """
    if not messages:
        return []

    n = len(messages)
    last_i = n - 1
    out: list[dict] = []

    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant":
            c = m.get("content") or ""
            out.append(
                {"role": "assistant", "content": c if isinstance(c, str) else str(c)}
            )
            continue

        if role == "user":
            if i == last_i:
                text = m.get("model_content")
                if text is None:
                    text = m.get("content") or ""
                if not isinstance(text, str):
                    text = str(text)
                u: dict = {"role": "user", "content": text}
                att = m.get("attachments")
                if att:
                    u["attachments"] = att
                out.append(u)
            else:
                c = m.get("content") or ""
                out.append(
                    {"role": "user", "content": c if isinstance(c, str) else str(c)}
                )
            continue

        c = m.get("content") or ""
        out.append(
            {"role": role or "user", "content": c if isinstance(c, str) else str(c)}
        )

    return out


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


# ── LangGraph streaming ────────────────────────────────────────────


def _collect_tool_names_from_updates(payload: dict[str, Any], acc: list[str]) -> None:
    for _node, inner in payload.items():
        if not isinstance(inner, dict):
            continue
        for m in inner.get("messages", []):
            for tc in getattr(m, "tool_calls", None) or []:
                n = (
                    tc.get("name")
                    if isinstance(tc, dict)
                    else getattr(tc, "name", None)
                )
                if n:
                    acc.append(n)


_TOOL_LABELS = {
    "create_course_pdf": "📄 Creating",
    "create_powerpoint_deck": "📊 Creating slides",
    "retrieve_from_knowledge_base": "🔍 Searching knowledge base",
}


def _stream_langgraph_agent(
    agent, messages: list[dict], tool_acc: list[str], *, thread_id: str = "default"
) -> Iterator[str]:
    config = {"configurable": {"thread_id": thread_id}}
    for chunk in agent.stream(
        {"messages": messages},
        config=config,
        stream_mode=["messages", "updates"],
    ):
        mode, payload = chunk[0], chunk[1]
        if mode == "messages":
            msg, meta = payload
            if meta.get("langgraph_node") not in ("model", "agent"):
                continue
            raw = getattr(msg, "content", None) or ""
            if isinstance(raw, list):
                # Anthropic returns content blocks — extract text only
                for block in raw:
                    if isinstance(block, dict) and block.get("type") == "text":
                        t = block.get("text", "")
                        if t:
                            yield t
                    elif isinstance(block, str) and block:
                        yield block
            elif isinstance(raw, str) and raw:
                yield raw
        elif mode == "updates" and isinstance(payload, dict):
            _collect_tool_names_from_updates(payload, tool_acc)
            import re as _re

            for node, inner in payload.items():
                if not isinstance(inner, dict):
                    continue
                for m in inner.get("messages", []):
                    # LLM decided to call a tool — emit "Creating…" with full args
                    for tc in getattr(m, "tool_calls", None) or []:
                        name = (
                            tc.get("name")
                            if isinstance(tc, dict)
                            else getattr(tc, "name", "")
                        )
                        args = (
                            tc.get("args")
                            if isinstance(tc, dict)
                            else getattr(tc, "args", {})
                        ) or {}
                        label = _TOOL_LABELS.get(name)
                        if label:
                            title = (
                                args.get("title")
                                or args.get("deck_title")
                                or args.get("question")
                                or ""
                            )
                            desc = f"{label}: {title}" if title else label
                            yield f"[PROG]{desc}"
                    # Tool finished — emit "Saved: filename"
                    content = getattr(m, "content", "") or ""
                    if "saved as '" in content:
                        match = _re.search(r"saved as '([^']+)'", content)
                        if match:
                            yield f"[PROG]✅ Saved: {match.group(1)}"


# ── public API ──────────────────────────────────────────────────────


@dataclass
class OrchestratorResult:
    reply: str
    agent_used: RouterChoice
    tool_names: list[str]


def iter_chat_turn_tokens(
    messages: list[dict],
    *,
    chat_id: int | str = "default",
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
    msgs = _messages_for_llm_turn([dict(m) for m in messages])

    try:
        if force_agent == "general":
            meta["agent_used"] = "general"
            yield from GeneralAgent.stream(_strip_for_text_agents(msgs))
            return

        if force_agent == "kb":
            meta["agent_used"] = "kb"
            yield from _stream_langgraph_agent(
                _get_kb_agent(),
                _strip_for_text_agents(msgs),
                tool_acc,
                thread_id=str(chat_id),
            )
            return

        if force_agent == "course":
            meta["agent_used"] = "course"
            base = _strip_for_text_agents(msgs)
            to_send = _inject_syllabus(base, syllabus) if syllabus_available else base
            yield from _stream_langgraph_agent(
                _get_course_agent(), to_send, tool_acc, thread_id=str(chat_id)
            )
            return

        if force_agent == "grading":
            meta["agent_used"] = "grading"
            yield from GradingAgent.stream(msgs)
            return

        # If the latest user turn has image attachments, only the grading agent
        # can see them — text agents strip vision content.
        latest_has_images = bool(
            msgs and msgs[-1].get("role") == "user" and msgs[-1].get("attachments")
        )
        if latest_has_images:
            choice = "grading"
        else:
            choice = RouterAgent.route(msgs, syllabus_available=syllabus_available)
        meta["agent_used"] = choice

        if choice == "general":
            yield from GeneralAgent.stream(_strip_for_text_agents(msgs))
            return

        if choice == "kb":
            yield from _stream_langgraph_agent(
                _get_kb_agent(),
                _strip_for_text_agents(msgs),
                tool_acc,
                thread_id=str(chat_id),
            )
            return

        if choice == "grading":
            yield from GradingAgent.stream(msgs)
            return

        if choice == "course":
            base = _strip_for_text_agents(msgs)
            to_send = _inject_syllabus(base, syllabus) if syllabus_available else base
            yield from _stream_langgraph_agent(
                _get_course_agent(), to_send, tool_acc, thread_id=str(chat_id)
            )
            return

        # Fallback — should not happen with a well-behaved router
        logger.warning("Unexpected router choice %r — falling back to general", choice)
        yield from GeneralAgent.stream(_strip_for_text_agents(msgs))
    except Exception:
        logger.exception("Error during chat turn (agent=%s)", meta.get("agent_used"))
        raise
    finally:
        meta["tool_names"] = list(dict.fromkeys(tool_acc))


def run_chat_turn(
    messages: list[dict],
    *,
    chat_id: int | str = "default",
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
        chat_id=chat_id,
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
