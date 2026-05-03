"""ORM model for ``fixity_records`` — CTS R7 fixity layer.

One row per (collection_id, document_filename); see
[`backend/alembic/versions/0079_fixity_records.py`](../alembic/versions/0079_fixity_records.py)
for the column rationale and the rationale for picking the latest
publication-origin version as the fixity scope.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class FixityStatus(str, enum.Enum):
    ok = "ok"
    drifted = "drifted"
    missing = "missing"
    error = "error"


class FixityRecord(Base):
    __tablename__ = "fixity_records"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "document_filename",
            name="uq_fixity_records_collection_filename",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    last_seen_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[FixityStatus] = mapped_column(
        SAEnum(FixityStatus, name="fixity_status", create_type=False),
        nullable=False,
        default=FixityStatus.ok,
    )
    first_recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    drifted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
