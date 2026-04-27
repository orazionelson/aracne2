"""Corpus — thematic grouping of public collections.

A corpus aggregates 0+ published, public collections under a single
label so an admin can carve out a research domain ("Shakespeare",
"Sommaria") without granting access to the entire instance. Today the
only consumer is the MCP server (which scopes its read tools to a
single corpus per token), but the entity is intentionally generic so
later features (workgroup membership, scoped search-engines, scoped
sitemaps) can attach to the same primitive.

Cascade rules:

* Deleting a corpus revokes every MCP token issued for it
  (``mcp_tokens.corpus_id`` is ``ON DELETE CASCADE`` — see migration).
* Deleting a collection silently removes its rows from
  ``corpus_collections`` (M:N association table, ``ON DELETE CASCADE``).
  The corpus survives with one fewer collection. Tokens stay valid
  but their effective scope shrinks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Table, Text, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


# M:N association — a collection can sit in multiple corpora (e.g.
# "Cancelleria Aragonese" can belong to both the "Sommaria" corpus
# and a broader "Diplomatica medievale" corpus).
corpus_collections = Table(
    "corpus_collections",
    Base.metadata,
    Column(
        "corpus_id",
        UUID(as_uuid=True),
        ForeignKey("corpora.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "collection_id",
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Corpus(Base):
    __tablename__ = "corpora"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # Loaded lazily; the admin views always need the collection list, so
    # service-layer queries use selectinload to avoid N+1.
    collections: Mapped[list["Collection"]] = relationship(  # noqa: F821 — TYPE_CHECKING
        "Collection",
        secondary=corpus_collections,
        backref="corpora",
        lazy="select",
    )


class McpToken(Base):
    """Bearer token an Admin issues to grant programmatic read access to a corpus.

    The plaintext value lives only in the response of the
    ``POST /corpora/{id}/tokens`` call. ``hashed_token`` is a bcrypt
    digest of the urlsafe-random plaintext; the auth path bcrypt-checks
    incoming bearer tokens against every non-revoked row of the corpus
    (small N — admins rarely have more than a handful per corpus).

    Revocation = setting ``revoked_at``. Rows are never hard-deleted so
    audit trails remain intact even after a token is rotated out.
    """

    __tablename__ = "mcp_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpora.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    hashed_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
