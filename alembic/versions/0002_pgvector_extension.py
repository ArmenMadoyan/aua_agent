"""Add pgvector extension for vector similarity search.

Revision ID: 0002_pgvector
Revises: 0001_initial
Create Date: 2025-05-10

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_pgvector"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
