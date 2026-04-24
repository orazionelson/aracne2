"""Codeberg plugin — ORM models.

Holds the per-collection link to a Codeberg (or self-hosted Forgejo)
repository: which repo the collection pushes to, which branch, the
optional per-link PAT override, and bookkeeping for the last push
and the one-shot Initialize flow.

One link per collection. The collection's ``slug`` is the natural
access key; lookup uses ``collection_id`` to survive slug changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CodebergCollectionLink(Base):
    """One Codeberg repo bound to one Aracne2 collection."""

    __tablename__ = "codeberg_collection_links"
    __table_args__ = (
        UniqueConstraint("collection_id", name="uq_codeberg_link_collection"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ``base_url`` defaults to codeberg.org but can point at any
    # Forgejo/Gitea deployment so institutional instances are supported
    # with the same plugin code.
    base_url: Mapped[str] = mapped_column(
        String(256), nullable=False, default="https://codeberg.org",
    )
    repo_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")

    # Fernet-encrypted PAT that overrides the plugin-global
    # ``codeberg_integration_pat`` setting for this link. ``NULL``
    # means "use the global PAT".
    pat_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Bookkeeping for the last successful push.
    last_push_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Set once by the Initialize flow (Phase 2). Once this is non-NULL
    # Initialize is permanently refused — preventing accidental
    # overwrites of a live collection.
    initialized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    initialized_from_sha: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )
