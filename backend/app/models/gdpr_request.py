"""ORM model for ``gdpr_requests``.

A queue between the authenticated user's "I want my data
anonymised" submission and the Admin's review + execution. Per
the editorial-platform posture (see
[GDPR_POSTURE.md](../../../docs/reference/GDPR_POSTURE.md)) the
delete-self path was removed: anonymisation is mediated, not
self-service, because the editorial record (authorship,
citations, scientific record-of-work) is third-party-affecting and
cannot be unilaterally retracted.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class GdprRequestKind(str, enum.Enum):
    """The only kind shipped today is ``anonymise``. Future kinds
    (``rectify_external``, ``restrict_processing``) would land here
    without a schema change since the column is a free-form string."""

    anonymise = "anonymise"


class GdprRequestStatus(str, enum.Enum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    completed = "completed"


class GdprRequest(Base):
    __tablename__ = "gdpr_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=GdprRequestStatus.submitted.value
    )
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    review_notes: Mapped[str | None] = mapped_column(Text, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
