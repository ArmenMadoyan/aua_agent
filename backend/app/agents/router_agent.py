"""Router agent — classifies user intent to pick the right specialist."""

from __future__ import annotations

import logging
from typing import Literal, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.app.llm import get_default_llm
from backend.app.prompts import ROUTE_DECISION_DESCRIPTION, ROUTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

RouterChoice = Literal["general", "kb", "course", "grading"]


class _RouteDecision(BaseModel):
    agent: RouterChoice = Field(description=ROUTE_DECISION_DESCRIPTION)


class RouterAgent:
    """Routes each user turn to the correct specialist agent."""

    @staticmethod
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

    @staticmethod
    def route(
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
            f"{RouterAgent._format_transcript(messages)}\n"
            "---"
        )
        router_llm = get_default_llm().with_structured_output(_RouteDecision)
        decision = router_llm.invoke(
            [
                SystemMessage(content=ROUTER_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        logger.info("Route decision: %s", decision.agent)
        return decision.agent
