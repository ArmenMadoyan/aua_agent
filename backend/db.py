from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    return url


async def init_db(database_url: str) -> None:
    global engine, AsyncSessionLocal
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set "
            "(e.g. postgresql://user:pass@localhost:5432/dbname)"
        )
    async_url = _to_async_url(database_url)
    engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def close_db() -> None:
    global engine, AsyncSessionLocal
    if engine:
        await engine.dispose()
    engine = None
    AsyncSessionLocal = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    async with AsyncSessionLocal() as session:
        yield session


def run_migrations() -> None:
    """Run Alembic migrations to head (sync, one-shot on startup)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    command.upgrade(cfg, "head")
