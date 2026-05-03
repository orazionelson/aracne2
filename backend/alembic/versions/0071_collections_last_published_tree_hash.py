"""Add ``collections.last_published_tree_hash`` for the publish idempotency guard.

The working/published split (Phase A1 of document versioning) decouples editor
edits from public visibility: edits go to ``/db/aracne2/collections/{slug}``,
the public reads from ``/db/aracne2/published/{slug}``, and ``publish_collection``
copies the former into the latter. Without a guard, any re-publish on
unchanged content re-fires every ``ON_COLLECTION_PUBLISHED`` listener (Zenodo,
Internet Archive, Dataverse, webhooks) and creates duplicate side effects.

This column stores a fingerprint of the working tree at the moment of the
last successful publish. The next publish compares the current working tree
fingerprint with this value and short-circuits before emitting the hook if
they match. The fingerprint is the SHA-256 of the concatenated, sorted
``(filename, content_sha256)`` pairs of every document in the collection.

Revision ID: 0071
Revises: 0070
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "last_published_tree_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "last_published_tree_hash")
