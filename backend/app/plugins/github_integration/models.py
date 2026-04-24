"""GitHub plugin — ORM models.

One link per collection / per website binding to a GitHub
repository. ``base_url`` defaults to github.com but can point at
GitHub Enterprise Server (``https://ghe.example.com``) — same
plugin code, same adapter, different host.

Mirrors the Codeberg plugin's model shape deliberately so both sets
of tables carry the same bookkeeping columns. The only reason the
tables are separate (rather than a single polymorphic ``forge_links``
table) is PAT isolation: each forge owns its own token column.
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


class GithubWebsiteLink(Base):
    """One GitHub repo bound to one Aracne2 website."""

    __tablename__ = "github_website_links"
    __table_args__ = (
        UniqueConstraint("website_id", name="uq_github_link_website"),
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
        String(256), nullable=False, default="https://github.com",
    )
    repo_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")

    pat_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_push_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_push_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now,
    )


class GithubCollectionLink(Base):
    """One GitHub repo bound to one Aracne2 collection."""

    __tablename__ = "github_collection_links"
    __table_args__ = (
        UniqueConstraint("collection_id", name="uq_github_link_collection"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )

    base_url: Mapped[str] = mapped_column(
        String(256), nullable=False, default="https://github.com",
    )
    repo_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")

    pat_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_push_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # One-shot Initialize bookkeeping (same semantics as Codeberg).
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
