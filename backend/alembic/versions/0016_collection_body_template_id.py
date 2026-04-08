"""add body_template_id FK to collections

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("body_template_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_collections_body_template_id",
        "collections",
        "body_templates",
        ["body_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_collections_body_template_id", "collections", type_="foreignkey")
    op.drop_column("collections", "body_template_id")
