"""Add ``policy_pages`` + ``policy_page_versions`` for FUTURE_IDEAS §27.

Phase PP-A of Milestone 3. Two tables:

- ``policy_pages``: one row per concrete instance of a built-in
  template (e.g. the deployment's Storage Policy). Carries the
  URL ``slug`` and a nullable FK to the version row currently
  exposed at ``/policies/<slug>``. ``published_version_id IS NULL``
  means the policy is in draft only — the public route 404s; only
  Editor+ readers can see the form.
- ``policy_page_versions``: append-only history of every Save.
  ``version_number`` is monotonic per ``policy_page_id``.
  ``content_jsonb`` carries the Field values keyed by Field name,
  with each value optionally a per-locale dict (e.g.
  ``{"it": "...", "en": "..."}``). ``content_sha256`` is the
  digest of the canonical-JSON serialisation, used by the audit
  trail and by future fixity-style integrity checks.

The two-table layout mirrors ``document_versions`` from M1 §7:
the same shape, scoped to policy pages instead of TEI documents.
No retention cap (per Q9 of the M3 brainstorm — append-only).

Revision ID: 0080
Revises: 0079
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_pages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("template_slug", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False, unique=True),
        sa.Column(
            "published_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("policy_page_versions.id", ondelete="SET NULL", use_alter=True, name="fk_policy_pages_published_version_id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("template_slug", name="uq_policy_pages_template_slug"),
    )

    op.create_table(
        "policy_page_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "policy_page_id",
            UUID(as_uuid=True),
            sa.ForeignKey("policy_pages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_jsonb", JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "saved_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "policy_page_id",
            "version_number",
            name="uq_policy_page_versions_page_version",
        ),
    )
    op.create_index(
        "ix_policy_page_versions_page_id",
        "policy_page_versions",
        ["policy_page_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_policy_page_versions_page_id", table_name="policy_page_versions"
    )
    op.drop_constraint(
        "fk_policy_pages_published_version_id",
        "policy_pages",
        type_="foreignkey",
    )
    op.drop_table("policy_page_versions")
    op.drop_table("policy_pages")
