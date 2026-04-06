"""plugin_data — generic key-value store for plugin-owned data

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin_data",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "plugin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plugins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
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

    # Lookup index on the full namespace (covers both NULL and non-NULL entity_id)
    op.create_index(
        "ix_plugin_data_namespace",
        "plugin_data",
        ["plugin_id", "entity_type", "entity_id", "key"],
    )

    # Uniqueness when entity_id IS NOT NULL
    op.execute(
        """
        CREATE UNIQUE INDEX uq_plugin_data_with_entity
        ON plugin_data (plugin_id, entity_type, entity_id, key)
        WHERE entity_id IS NOT NULL
        """
    )

    # Uniqueness when entity_id IS NULL (two NULLs would otherwise not clash)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_plugin_data_no_entity
        ON plugin_data (plugin_id, entity_type, key)
        WHERE entity_id IS NULL
        """
    )

    # Trigger to keep updated_at in sync
    op.execute(
        """
        CREATE TRIGGER trg_plugin_data_updated_at
        BEFORE UPDATE ON plugin_data
        FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_plugin_data_updated_at ON plugin_data")
    op.execute("DROP INDEX IF EXISTS uq_plugin_data_no_entity")
    op.execute("DROP INDEX IF EXISTS uq_plugin_data_with_entity")
    op.drop_index("ix_plugin_data_namespace", table_name="plugin_data")
    op.drop_table("plugin_data")
