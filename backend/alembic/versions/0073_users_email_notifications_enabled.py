"""Add ``users.email_notifications_enabled`` for the workflow email toggle.

Phase EM-A of the email channels feature. Each user gets a single
boolean "send me workflow emails" knob that gates the three workflow
events (collection submitted / rejected / published). Transactional
emails (password reset, when EM-C ships) bypass this toggle so users can
always recover their account.

Default ``TRUE`` so existing rows get the safe-by-default opt-in: the
overall feature is also gated by ``system_settings.email_enabled``
(default ``"false"``), so flipping the platform-level switch is the
explicit step the operator must take before anything reaches a relay.

Revision ID: 0073
Revises: 0072
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "email_notifications_enabled")
