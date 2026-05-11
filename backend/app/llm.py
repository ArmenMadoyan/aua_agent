"""Shared Claude LLM singletons for all agents."""

from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL


@lru_cache(maxsize=1)
def get_default_llm() -> ChatAnthropic:
    """Temperature 0 — used by KB agent and router."""
    return ChatAnthropic(
        model=ANTHROPIC_MODEL,
        anthropic_api_key=ANTHROPIC_API_KEY,
        temperature=0,
    )


@lru_cache(maxsize=1)
def get_creative_llm() -> ChatAnthropic:
    """Temperature 0.35 — used by course agent."""
    return ChatAnthropic(
        model=ANTHROPIC_MODEL,
        anthropic_api_key=ANTHROPIC_API_KEY,
        temperature=0.35,
    )


@lru_cache(maxsize=1)
def get_general_llm() -> ChatAnthropic:
    """Temperature 0.2 — used by general chat and grading."""
    return ChatAnthropic(
        model=ANTHROPIC_MODEL,
        anthropic_api_key=ANTHROPIC_API_KEY,
        temperature=0.2,
    )
