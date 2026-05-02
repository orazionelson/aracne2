"""Composite indexes for the audit-log admin view (FUTURE_IDEAS §20).

The view hits the table with three predictable access patterns:

1. Latest-first by time (default landing query, no filter).
2. By actor over a time range (the "what did user X do this week"
   path).
3. By action over a time range (the "every collection.deleted in
   the last 30 days" path).

A 90-day retention window in a busy multi-editor deployment can
reach low-millions of rows, so a sequential scan is not acceptable.
We add three indexes:

- ``ix_audit_log_occurred_at_desc`` for the latest-first scan;
- ``ix_audit_log_actor_id_occurred_at_desc`` for the actor case;
- ``ix_audit_log_action_occurred_at_desc`` for the action case.

The ``DESC`` suffix on every column keeps the planner from doing a
backward scan when ``ORDER BY occurred_at DESC`` is the only sort
the view ever issues.

Revision ID: 0078
Revises: 0077
Create Date: 2026-05-03
"""

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_log_occurred_at_desc",
        "audit_log",
        [op.f("occurred_at")],
        postgresql_using="btree",
        postgresql_ops={"occurred_at": "DESC"},
    )
    op.create_index(
        "ix_audit_log_actor_id_occurred_at_desc",
        "audit_log",
        ["actor_id", "occurred_at"],
        postgresql_using="btree",
        postgresql_ops={"occurred_at": "DESC"},
    )
    op.create_index(
        "ix_audit_log_action_occurred_at_desc",
        "audit_log",
        ["action", "occurred_at"],
        postgresql_using="btree",
        postgresql_ops={"occurred_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_action_occurred_at_desc", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id_occurred_at_desc", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at_desc", table_name="audit_log")
