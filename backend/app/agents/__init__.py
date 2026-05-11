"""Agent classes for the AUA assistant."""

from backend.app.agents.kb_agent import KBAgent
from backend.app.agents.course_agent import CourseAgent
from backend.app.agents.general_agent import GeneralAgent
from backend.app.agents.grading_agent import GradingAgent
from backend.app.agents.router_agent import RouterAgent

__all__ = [
    "KBAgent",
    "CourseAgent",
    "GeneralAgent",
    "GradingAgent",
    "RouterAgent",
]
