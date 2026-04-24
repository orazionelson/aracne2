"""GitLab plugin — ORM models.

Holds the per-collection / per-website link to a GitLab repository
(gitlab.com or any self-hosted GitLab instance via ``base_url``).
The bookkeeping columns mirror the Codeberg and GitHub plugin
models intentionally so a future refactor can extract the common
shape into a polymorphic table without breaking existing data.

One link per collection (and one per website). Lookup uses the
foreign-key id to survive slug changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class GitlabWebsiteLink(Base):
    """One Gitlab repo bound to one Aracne2 website.

    Symmetric to :class:`GitlabCollectionLink` but scoped to a
    Website (rendered HTML/CSS/JS output) instead of a Collection
    (raw TEI sources). Push direction only — websites are derived
    artefacts, never imported from a forge.
    """

    __tablename__ = "gitlab_website_links"
    __table_args__ = (
        UniqueConstraint("website_id", name="uq_gitlab_link_website"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
    )

    base_url: Mapped[str] = mapped_column(
        String(256), nullable=False, default="https://gitlab.com",
    )
    # Wider than the other forges: GitLab supports nested group paths
    # like ``group/subgroup/leafgroup`` in this slot.
    repo_owner: Mapped[str] = mapped_column(String(256), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")

    pat_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_push_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Number of files in the last successful push — cheap bookkeeping
    # so the UI can show "Last push: 42 files" without re-reading the
    # site tree.
    last_push_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )


class GitlabCollectionLink(Base):
    """One Gitlab repo bound to one Aracne2 collection."""

    __tablename__ = "gitlab_collection_links"
    __table_args__ = (
        UniqueConstraint("collection_id", name="uq_gitlab_link_collection"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ``base_url`` defaults to gitlab.org but can point at any
    # Forgejo/Gitea deployment so institutional instances are supported
    # with the same plugin code.
    base_url: Mapped[str] = mapped_column(
        String(256), nullable=False, default="https://gitlab.com",
    )
    # Wider than the other forges: GitLab supports nested group paths
    # like ``group/subgroup/leafgroup`` in this slot.
    repo_owner: Mapped[str] = mapped_column(String(256), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")

    # Fernet-encrypted PAT that overrides the plugin-global
    # ``gitlab_integration_pat`` setting for this link. ``NULL``
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
