"""Centralized prompt constants for all agents."""

from backend.app.prompts.kb_agent import KB_SYSTEM_PROMPT
from backend.app.prompts.course_agent import COURSE_SYSTEM_PROMPT
from backend.app.prompts.general_agent import GENERAL_SYSTEM_PROMPT
from backend.app.prompts.router_agent import (
    ROUTER_SYSTEM_PROMPT,
    ROUTE_DECISION_DESCRIPTION,
)
from backend.app.prompts.grading_agent import GRADING_SYSTEM_PROMPT

__all__ = [
    "KB_SYSTEM_PROMPT",
    "COURSE_SYSTEM_PROMPT",
    "GENERAL_SYSTEM_PROMPT",
    "ROUTER_SYSTEM_PROMPT",
    "ROUTE_DECISION_DESCRIPTION",
    "GRADING_SYSTEM_PROMPT",
]
