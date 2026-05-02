"""Add ``nl_search_budget_day`` — per-day spend / queries counter.

Phase NLS-A. The natural-language search plugin caps spend at
``nl_search_daily_budget_eur`` per UTC day; each LLM call adds its
estimated cost (input/output tokens × per-model EUR rate) to today's
row and the endpoint short-circuits to 503 when the cap is exceeded.

Ollama runs report ``eur_spent = 0`` since the local provider has no
$ cost — the row still tracks ``queries`` so the operator can see
volume even when the budget is irrelevant.

Revision ID: 0077
Revises: 0076
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nl_search_budget_day",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column(
            "eur_spent",
            sa.Numeric(precision=10, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "queries",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_table("nl_search_budget_day")
