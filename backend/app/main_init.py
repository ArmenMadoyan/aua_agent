"""Checkpointer initialization — separated from agent classes for clean startup."""

from __future__ import annotations

import logging

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from backend.config import DATABASE_URL

logger = logging.getLogger(__name__)

_checkpointer: PostgresSaver | None = None
_pg_conn: psycopg.Connection | None = None


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

    logger.info("Initializing PostgresSaver checkpointer")
    setup_conn = psycopg.connect(conn_string, autocommit=True)
    PostgresSaver(conn=setup_conn).setup()
    setup_conn.close()

    _pg_conn = psycopg.connect(conn_string)
    _checkpointer = PostgresSaver(conn=_pg_conn)
    logger.info("Checkpointer ready")
    return _checkpointer


def get_checkpointer() -> PostgresSaver | None:
    return _checkpointer
