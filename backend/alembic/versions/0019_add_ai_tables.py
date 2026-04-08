"""add ai_prompts and ai_request_logs tables

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_prompts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("context_vars", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("target_context", sa.String(64), nullable=True),
        sa.Column(
            "is_native",
            sa.Boolean,
            nullable=False,
            server_default="FALSE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ai_request_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("prompt_slug", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_request_logs")
    op.drop_table("ai_prompts")
