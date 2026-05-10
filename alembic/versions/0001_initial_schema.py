"""Initial schema: llm_models, conversations, messages, aua_policies (RAG).

Tables (PostgreSQL names):
- llm_models: id, model_id, title, is_default, display_order, created_at, updated_at
- conversations: id (conversation id), user_id, title, created_at, updated_at
- messages: id, conversation_id, role, content, agent_name, agent_id, llm_model_id,
  tools_called (JSONB), created_at
- aua_policies: policy KB chunks with content + embedding (double precision[], no extension)

Revision ID: 0001_initial
Revises:
Create Date: 2025-03-22

"""
from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _embedding_dim() -> int:
    return int(os.getenv("EMBEDDING_DIMENSION", "1536"))


def upgrade() -> None:
    op.create_table(
        "llm_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", name="uq_llm_models_model_id"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("llm_model_id", sa.Integer(), nullable=True),
        sa.Column("tools_called", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["llm_model_id"],
            ["llm_models.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    dim = _embedding_dim()
    op.create_table(
        "aua_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doc_hash", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            postgresql.ARRAY(sa.Float()),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"cardinality(embedding) = {dim}",
            name="ck_aua_policies_embedding_dim",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_aua_policies_doc_hash",
        "aua_policies",
        ["doc_hash"],
        unique=False,
    )

    op.execute(
        sa.text("""
            INSERT INTO llm_models (model_id, title, is_default, display_order)
            VALUES ('gpt-4.1', 'GPT-4.1', true, 0)
            ON CONFLICT (model_id) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_index("idx_aua_policies_doc_hash", table_name="aua_policies")
    op.drop_table("aua_policies")
    op.drop_table("conversations")
    op.drop_table("llm_models")
