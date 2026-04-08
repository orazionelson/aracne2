"""create collection_validation_runs table

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE validation_run_status AS ENUM ('pending', 'running', 'done', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.create_table(
        "collection_validation_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("schema_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "done", "failed",
                name="validation_run_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("doc_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("validated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("results", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_collection_validation_runs_collection_id",
        "collection_validation_runs",
        ["collection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_validation_runs_collection_id",
        table_name="collection_validation_runs",
    )
    op.drop_table("collection_validation_runs")
    op.execute("DROP TYPE IF EXISTS validation_run_status")
