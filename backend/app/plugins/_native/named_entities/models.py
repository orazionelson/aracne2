"""SQLAlchemy models for the Named Entity Index plugin."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class NamedEntity(Base):
    __tablename__ = "named_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Open string — any TEI local-name() value, e.g. "persName", "objectName", "measure".
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Canonical display form — the "standard" label for this entity.
    # First occurrence's text is used; can be corrected by an admin.
    canonical_form: Mapped[str] = mapped_column(String(512), nullable=False)
    # External authority URI (VIAF, GeoNames, Wikidata, etc.) — optional.
    authority_ref: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None
    )
    # Denormalized total occurrence count across all collections.
    # Refreshed after every index/deindex operation.
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    occurrences: Mapped[list["EntityOccurrence"]] = relationship(
        "EntityOccurrence", back_populates="entity", cascade="all, delete-orphan"
    )


class EntityOccurrence(Base):
    __tablename__ = "entity_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("named_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    # Text as it actually appears in the document (may differ from canonical_form).
    raw_form: Mapped[str] = mapped_column(String(512), nullable=False)
    # Surrounding sentence / paragraph excerpt (up to 300 chars).
    context: Mapped[str | None] = mapped_column(String(300), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    entity: Mapped["NamedEntity"] = relationship("NamedEntity", back_populates="occurrences")
