"""General-purpose chat agent — no tools, direct LLM streaming."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.app.llm import get_general_llm
from backend.app.prompts import GENERAL_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeneralAgent:
    """Handles general chat — greetings, generic Q&A, non-specialist topics."""

    @staticmethod
    def _build_lc_messages(messages: list[dict]) -> list:
        lc: list = [SystemMessage(content=GENERAL_SYSTEM_PROMPT)]
        for m in messages:
            if m.get("role") == "user":
                c = m.get("content")
                if not isinstance(c, str):
                    c = str(c) if c is not None else ""
                lc.append(HumanMessage(content=c))
            elif m.get("role") == "assistant":
                lc.append(AIMessage(content=m.get("content") or ""))
        return lc

    @staticmethod
    def stream(messages: list[dict]) -> Iterator[str]:
        logger.info("GeneralAgent streaming response")
        lc = GeneralAgent._build_lc_messages(messages)
        for chunk in get_general_llm().stream(lc):
            raw = getattr(chunk, "content", None)
            if not raw:
                continue
            if isinstance(raw, list):
                for block in raw:
                    if isinstance(block, dict) and block.get("type") == "text":
                        t = block.get("text", "")
                        if t:
                            yield t
                    elif isinstance(block, str) and block:
                        yield block
            elif isinstance(raw, str):
                yield raw
