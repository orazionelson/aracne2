"""create named_entities and entity_occurrences tables

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type safely (no CREATE TYPE IF NOT EXISTS in PostgreSQL)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE entity_type AS ENUM ('person', 'place', 'org');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.create_table(
        "named_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "type",
            ENUM(name="entity_type", create_type=False),
            nullable=False,
        ),
        sa.Column("canonical_form", sa.String(512), nullable=False),
        sa.Column("authority_ref", sa.String(1024), nullable=True),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_named_entities_type", "named_entities", ["type"])
    op.create_index(
        "ix_named_entities_canonical_form",
        "named_entities",
        [sa.text("lower(canonical_form)")],
    )
    op.create_index(
        "ix_named_entities_occurrence_count",
        "named_entities",
        ["occurrence_count"],
    )

    op.create_table(
        "entity_occurrences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("named_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("raw_form", sa.String(512), nullable=False),
        sa.Column("context", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_entity_occurrences_entity_id", "entity_occurrences", ["entity_id"])
    op.create_index(
        "ix_entity_occurrences_collection_filename",
        "entity_occurrences",
        ["collection_id", "filename"],
    )


def downgrade() -> None:
    op.drop_table("entity_occurrences")
    op.drop_table("named_entities")
    op.execute("DROP TYPE IF EXISTS entity_type;")
