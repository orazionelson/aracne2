"""Add ``document_versions`` table for the document versioning feature
(Phase B of Milestone 1).

Each row is a snapshot of a single document's XML content captured at an
editorially meaningful moment:

- ``creation``     — first ``put_document`` of a filename in a collection
- ``manual``       — Editor+ pressed "Save version" with a free-text message
- ``submission``   — collection.submitted_for_review fired (per-doc snapshot)
- ``rejection``    — review→assigned transition (per-doc snapshot)
- ``publication``  — collection.published / direct_published (per-doc snapshot)
- ``rollback``     — the doc's HEAD was rebuilt from a previous version

Snapshots are full-blob, gzip-compressed XML in BYTEA. A SHA-256 of the
*uncompressed* content is stored alongside so:

1. The publish path can dedupe on identical content (skip-on-unchanged).
2. The Milestone 2 fixity scheduler reads ``content_sha256`` directly
   without re-hashing every blob.

The ``audit_log_id`` back-pointer ties each version row to the audit_log
event that originated it; ``audit_log.id`` is BigInteger, not UUID, so the
FK column type matches.

Indexes:

- Unique ``(collection_id, document_filename, version_number)`` so the
  per-document version counter is monotonic.
- ``ix_doc_versions_lookup(collection_id, document_filename, created_at)``
  supports the future CLI ``aracne export --as-of 2026-Q1`` query and
  the editor's "show history of this doc" panel.
- ``ix_doc_versions_origin_filter(collection_id, document_filename, origin)``
  supports the public ``?version=N`` permalink (which must reject any
  non-publication origin) and the version-list API's ``?origin=publication``
  filter.

Revision ID: 0072
Revises: 0071
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


_VERSION_ORIGIN_VALUES = (
    "creation",
    "manual",
    "submission",
    "rejection",
    "publication",
    "rollback",
)


def upgrade() -> None:
    # Enum type — created via a DO block so re-runs after a partial failure
    # do not blow up on DuplicateObjectError. Mirrors the project pattern.
    values_sql = ", ".join(f"'{v}'" for v in _VERSION_ORIGIN_VALUES)
    op.execute(
        f"""
        DO $$ BEGIN
            CREATE TYPE version_origin AS ENUM ({values_sql});
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "document_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_filename", sa.String(length=255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("xml_content", sa.LargeBinary(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "origin",
            ENUM(name="version_origin", create_type=False),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "audit_log_id",
            sa.BigInteger(),
            sa.ForeignKey("audit_log.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "collection_id",
            "document_filename",
            "version_number",
            name="uq_doc_versions_collection_filename_version",
        ),
    )
    op.create_index(
        "ix_doc_versions_lookup",
        "document_versions",
        ["collection_id", "document_filename", "created_at"],
    )
    op.create_index(
        "ix_doc_versions_origin_filter",
        "document_versions",
        ["collection_id", "document_filename", "origin"],
    )


def downgrade() -> None:
    op.drop_index("ix_doc_versions_origin_filter", table_name="document_versions")
    op.drop_index("ix_doc_versions_lookup", table_name="document_versions")
    op.drop_table("document_versions")
    op.execute("DROP TYPE IF EXISTS version_origin")
