"""add cancelled to validation_run_status enum

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-08
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL supports ADD VALUE IF NOT EXISTS since 9.6.
    op.execute("ALTER TYPE validation_run_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    # PostgreSQL has no DROP VALUE for enum types; the only way to remove a value
    # is to drop and recreate the type.  Rows with status='cancelled' are
    # demoted to 'failed' first so the cast below succeeds.
    op.execute(
        "UPDATE collection_validation_runs"
        " SET status = 'failed'"
        " WHERE status = 'cancelled'"
    )
    op.execute(
        "CREATE TYPE validation_run_status_new"
        " AS ENUM ('pending', 'running', 'done', 'failed')"
    )
    op.execute(
        "ALTER TABLE collection_validation_runs"
        " ALTER COLUMN status TYPE validation_run_status_new"
        " USING status::text::validation_run_status_new"
    )
    op.execute("DROP TYPE validation_run_status")
    op.execute("ALTER TYPE validation_run_status_new RENAME TO validation_run_status")
