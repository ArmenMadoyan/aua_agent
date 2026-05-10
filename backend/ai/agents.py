"""LangGraph agents with PostgresSaver checkpointing."""

from __future__ import annotations

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

from backend.config import DATABASE_URL, OPENAI_API_KEY as API_KEY
from backend.ai.course_tools import create_course_pdf, create_powerpoint_deck
from backend.ai.tools import retrieve_from_knowledge_base

_checkpointer: PostgresSaver | None = None
_pg_conn: psycopg.Connection | None = None

_kb_agent = None
_course_agent = None

_KB_SYSTEM_PROMPT = (
    "You are a helpful assistant for the American University of Armenia (AUA). "
    "You answer questions using the AUA policy PDF knowledge base via the "
    "`retrieve_from_knowledge_base` tool. Use the tool when the user asks about "
    "AUA policies, procedures, rules, academic matters, HR, facilities, admissions, "
    "conduct, or any official AUA information. If the question is about general "
    "knowledge or unrelated to AUA, you may answer without the tool. Always cite "
    "the policy document (file name) when you use retrieved content. Prioritize "
    "accuracy and base answers on the retrieved policy text when relevant."
)

_COURSE_SYSTEM_PROMPT = (
    "You help instructors prepare course materials. When the user wants slides, "
    "you MUST call `create_powerpoint_deck` with a short deck_title and slides_text "
    "in this exact pattern: each slide starts with a line 'SLIDE: Title' then lines "
    "with bullets starting with '- '. Build substantive content from the user's "
    "syllabus, topic list, or instructions. "
    "When the user wants homework, quizzes, a midterm, a final, or any written "
    "assessment as a file, you MUST call `create_course_pdf` with document_type "
    "(homework, quiz, midterm, final_exam, or other), title, and a full body with "
    "questions and instructions in plain text (sections separated by blank lines). "
    "Never paste a full exam or homework only as chat text when they asked for a file—use the tool. "
    "If the request is vague (e.g. 'make course content' without saying slides vs "
    "exams), ask briefly what they need and which topics or syllabus to use—then "
    "use the tools once you know. After each tool call, tell the user the filename "
    "and that they can download it from the /course/artifacts/ URL path on the API."
)


def _pg_conn_string() -> str:
    url = DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


def init_checkpointer() -> PostgresSaver:
    global _checkpointer, _pg_conn
    conn_string = _pg_conn_string()

    setup_conn = psycopg.connect(conn_string, autocommit=True)
    PostgresSaver(conn=setup_conn).setup()
    setup_conn.close()

    _pg_conn = psycopg.connect(conn_string)
    _checkpointer = PostgresSaver(conn=_pg_conn)
    return _checkpointer


def get_checkpointer() -> PostgresSaver | None:
    return _checkpointer


def _build_agents() -> None:
    global _kb_agent, _course_agent

    llm = ChatOpenAI(
        model_name="gpt-4.1",
        openai_api_key=API_KEY,
        temperature=0,
    )
    _kb_agent = create_react_agent(
        model=llm,
        tools=[retrieve_from_knowledge_base],
        prompt=_KB_SYSTEM_PROMPT,
        checkpointer=_checkpointer,
    )

    course_llm = ChatOpenAI(
        model_name="gpt-4.1",
        openai_api_key=API_KEY,
        temperature=0.35,
    )
    _course_agent = create_react_agent(
        model=course_llm,
        tools=[create_powerpoint_deck, create_course_pdf],
        prompt=_COURSE_SYSTEM_PROMPT,
        checkpointer=_checkpointer,
    )


def get_kb_agent():
    if _kb_agent is None:
        _build_agents()
    return _kb_agent


def get_course_agent():
    if _course_agent is None:
        _build_agents()
    return _course_agent
