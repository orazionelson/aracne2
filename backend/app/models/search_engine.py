"""SQLAlchemy ORM models for search engines."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class SearchEngine(Base):
    __tablename__ = "search_engines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    # Optional XSLT template applied to each XML result before returning HTML.
    # When null, the raw XML is returned as plain text.
    xslt_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xslt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    collections: Mapped[list["SearchEngineCollection"]] = relationship(
        "SearchEngineCollection",
        back_populates="search_engine",
        cascade="all, delete-orphan",
    )


class SearchEngineCollection(Base):
    """Junction table linking a search engine to its target collections."""

    __tablename__ = "search_engine_collections"

    search_engine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_engines.id", ondelete="CASCADE"),
        primary_key=True,
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )

    search_engine: Mapped["SearchEngine"] = relationship(
        "SearchEngine", back_populates="collections"
    )
