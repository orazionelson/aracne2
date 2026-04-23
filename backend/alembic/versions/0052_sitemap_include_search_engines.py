"""Seed the ``sitemap_include_search_engines`` opt-in setting.

Drives whether ``/sitemap.xml`` includes the search-engine sub-sitemap
(and, recursively, whether ``/sitemap-search-engines.xml`` returns
content or an empty urlset). Default is ``false`` — the search-page
HTML is built per-engine and doesn't always make sense as a crawl
target; admins that do want it opt in explicitly.

Revision ID: 0052
Revises: 0051
Create Date: 2026-04-23
"""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, type)
        VALUES ('sitemap_include_search_engines', 'false', 'bool')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_settings WHERE key = 'sitemap_include_search_engines';"
    )
