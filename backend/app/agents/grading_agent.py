"""Grading agent — vision-based homework scoring with rubric."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.app.llm import get_general_llm
from backend.app.prompts import GRADING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GradingAgent:
    """Scores/evaluates student work using vision and a rubric."""

    @staticmethod
    def build_lc_messages(messages: list[dict[str, Any]]) -> list:
        """Turn chat dicts (optional ``attachments`` on user turns) into LangChain messages."""
        logger.info(
            "Building grading LangChain messages from %d chat messages", len(messages)
        )
        last_user_i: int | None = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_i = i
                break

        lc: list = [SystemMessage(content=GRADING_SYSTEM_PROMPT)]
        for i, m in enumerate(messages):
            role = m.get("role")
            content = m.get("model_content")
            if content is None:
                content = m.get("content")
            if content is None:
                content = ""
            if not isinstance(content, str):
                content = str(content)

            if role == "user":
                attachments = list(m.get("attachments") or [])
                if last_user_i is not None and i != last_user_i:
                    attachments = []
                if attachments:
                    parts: list[dict[str, Any]] = []
                    if content.strip():
                        parts.append({"type": "text", "text": content})
                    for spec in attachments:
                        mt = spec.get("mime_type") or "image/png"
                        b64 = spec.get("base64") or ""
                        if not b64:
                            continue
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mt};base64,{b64}"},
                            }
                        )
                    if len(parts) == 1 and parts[0].get("type") == "image_url":
                        parts.insert(
                            0,
                            {
                                "type": "text",
                                "text": "Please look at this image and help me with it.",
                            },
                        )
                    lc.append(HumanMessage(content=parts))
                else:
                    lc.append(HumanMessage(content=content))
            elif role == "assistant":
                lc.append(AIMessage(content=content))
        return lc

    @staticmethod
    def stream(messages: list[dict]) -> Iterator[str]:
        logger.info("GradingAgent streaming response")
        lc = GradingAgent.build_lc_messages(messages)
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
