"""tei_schemas — TEI schema registry + collections.schema_id FK

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create schema_format enum safely (idempotent)
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE schema_format AS ENUM ('rng', 'dtd', 'xsd');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "tei_schemas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        # Validation schema file info (RNG / DTD / XSD)
        sa.Column("validation_filename", sa.String(512), nullable=True),
        sa.Column(
            "validation_format",
            postgresql.ENUM(name="schema_format", create_type=False),
            nullable=True,
        ),
        # CM5 autocomplete schema file info
        sa.Column("cm5_filename", sa.String(512), nullable=True),
        # Audit
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Add schema_id FK to collections (nullable — existing rows keep NULL)
    op.add_column(
        "collections",
        sa.Column("schema_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_collections_schema_id",
        "collections",
        "tei_schemas",
        ["schema_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_collections_schema_id", "collections", type_="foreignkey")
    op.drop_column("collections", "schema_id")
    op.drop_table("tei_schemas")
    op.execute("DROP TYPE IF EXISTS schema_format")
