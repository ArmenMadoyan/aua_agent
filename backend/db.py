import os
from contextlib import contextmanager
from typing import List, Literal, TypedDict

from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

# OpenAI text-embedding-ada-002 / text-embedding-3-small default width
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
DEFAULT_USER_ID = int(os.getenv("DEFAULT_USER_ID", "1"))


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set (e.g. postgresql://user:pass@localhost:5432/dbname)"
        )
    return url


@contextmanager
def get_connection():
    conn = connect(_database_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Apply Alembic migrations to head (schema: llm_models, conversations, messages, aua_policies)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    command.upgrade(cfg, "head")


def create_session(user_id: int | None = None, title: str | None = None) -> int:
    uid = DEFAULT_USER_ID if user_id is None else user_id
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (user_id, title)
                VALUES (%s, %s)
                RETURNING id
                """,
                (uid, title),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row["id"])


Role = Literal["user", "assistant"]


def _default_llm_model_id(cur) -> int | None:
    cur.execute(
        """
        SELECT id FROM llm_models
        WHERE is_default = true
        ORDER BY display_order, id
        LIMIT 1
        """
    )
    row = cur.fetchone()
    return int(row["id"]) if row else None


def add_message(
    session_id: int,
    role: Role,
    content: str,
    *,
    agent_name: str | None = None,
    agent_id: str | None = None,
    llm_model_id: int | None = None,
    tools_called: list[str] | None = None,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            model_id = llm_model_id
            if role == "assistant" and model_id is None:
                model_id = _default_llm_model_id(cur)

            tools_json = Jsonb(tools_called) if tools_called is not None else None

            cur.execute(
                """
                INSERT INTO messages (
                    conversation_id, role, content,
                    agent_name, agent_id, llm_model_id, tools_called
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    role,
                    content,
                    agent_name,
                    agent_id,
                    model_id,
                    tools_json,
                ),
            )
            cur.execute(
                """
                UPDATE conversations SET updated_at = now() WHERE id = %s
                """,
                (session_id,),
            )


class Message(TypedDict):
    role: Role
    content: str


def get_messages(session_id: int) -> list[Message]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = %s
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
    return [Message(role=row["role"], content=row["content"]) for row in rows]


def _ts_str(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class Session(TypedDict):
    id: int
    created_at: str
    title: str | None


def list_sessions() -> List[Session]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, created_at, title FROM conversations
                ORDER BY updated_at DESC, id DESC
                """
            )
            rows = cur.fetchall()
    return [
        Session(
            id=int(row["id"]),
            created_at=_ts_str(row["created_at"]),
            title=row["title"],
        )
        for row in rows
    ]


def session_exists(session_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM conversations WHERE id = %s", (session_id,))
            return cur.fetchone() is not None


def delete_session(session_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM conversations WHERE id = %s RETURNING id",
                (session_id,),
            )
            return cur.fetchone() is not None


def get_default_llm_model_id() -> int | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            return _default_llm_model_id(cur)
