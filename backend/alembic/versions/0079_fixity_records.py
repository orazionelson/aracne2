"""Add ``fixity_records`` — per-(collection, filename) integrity tracker.

Phase M2-C of Milestone 2. Closes the most visible CTS R7 gap: the
platform now records the SHA-256 hash of every published document
at deposit time and re-checks it on a scheduled cadence; drift
between *expected_sha256* (recorded once) and *last_seen_sha256*
(observed on the last re-check) surfaces in /admin/fixity.

One row per (collection_id, document_filename). The fixity scope is
the **latest publication-origin version** of the file (per Q8 of
the M2 brainstorm) — much cheaper to re-check than walking every
``document_versions`` row, and what the public actually sees.

Status enum:

- ``ok``       — last re-check matched expected_sha256
- ``drifted``  — last re-check returned a different SHA-256
- ``missing``  — the published row has gone, e.g. unpublish or
                 manual delete; surfaces as a drift signal
- ``error``    — the re-check job could not read the version
                 (transient issue, retried at the next run)

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE fixity_status AS ENUM ('ok', 'drifted', 'missing', 'error');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "fixity_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_filename", sa.String(length=255), nullable=False
        ),
        sa.Column(
            "expected_sha256", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "last_seen_sha256", sa.String(length=64), nullable=True
        ),
        sa.Column(
            "version_number", sa.Integer(), nullable=False
        ),
        sa.Column(
            "size_bytes", sa.Integer(), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("ok", "drifted", "missing", "error", name="fixity_status", create_type=False),
            nullable=False,
            server_default=sa.text("'ok'"),
        ),
        sa.Column(
            "first_recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "drifted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "collection_id",
            "document_filename",
            name="uq_fixity_records_collection_filename",
        ),
    )
    op.create_index(
        "ix_fixity_records_status",
        "fixity_records",
        ["status"],
    )
    op.create_index(
        "ix_fixity_records_collection_id",
        "fixity_records",
        ["collection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fixity_records_collection_id", table_name="fixity_records")
    op.drop_index("ix_fixity_records_status", table_name="fixity_records")
    op.drop_table("fixity_records")
    op.execute("DROP TYPE IF EXISTS fixity_status;")
