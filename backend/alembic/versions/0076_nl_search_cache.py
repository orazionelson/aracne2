"""Add ``nl_search_cache`` — identical-query response cache.

Phase NLS-A of the natural-language search plugin. A cheap key/value
store keyed on the SHA-256 of ``(corpus_id, provider, model, query)``
so the second visitor asking the same question does not burn another
LLM round-trip. Default TTL is 60 minutes
(``nl_search_cache_ttl_minutes``); the orchestrator stamps
``expires_at`` at write time and lookups filter by it.

``hits`` is a small counter the operator can read to gauge how much
the cache is actually saving. Non-critical — never read on the hot
path. ``response_json`` is a serialised SSE-event list the endpoint
replays verbatim on a hit.

Revision ID: 0076
Revises: 0075
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nl_search_cache",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "hits",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_nl_search_cache_expires_at",
        "nl_search_cache",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nl_search_cache_expires_at",
        table_name="nl_search_cache",
    )
    op.drop_table("nl_search_cache")
