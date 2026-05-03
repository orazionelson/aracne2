"""Add ``gdpr_requests`` for the editor-appropriate GDPR posture.

The platform's "delete-self" endpoint is going away (the B2C
self-service shape is wrong for a scientific editor — see
[GDPR_POSTURE.md](../../../docs/reference/GDPR_POSTURE.md)). In its
place, an authenticated user submits a *request* that an Admin
reviews; on approval the Admin runs the targeted anonymise action
that scrubs identifying metadata while preserving the editorial
record (authorship of published documents, audit trail integrity).

This table is the queue between the user's submission and the
Admin's review. One open request per user per kind; re-submitting
while one is open returns 409 from the service layer.

Revision ID: 0082
Revises: 0081
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gdpr_requests",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'submitted'"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_gdpr_requests_user_id",
        "gdpr_requests",
        ["user_id"],
    )
    op.create_index(
        "ix_gdpr_requests_status",
        "gdpr_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_gdpr_requests_status", table_name="gdpr_requests")
    op.drop_index("ix_gdpr_requests_user_id", table_name="gdpr_requests")
    op.drop_table("gdpr_requests")
