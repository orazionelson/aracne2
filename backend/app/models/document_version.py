"""ORM model for the ``document_versions`` table.

A row captures the full XML content of a single document at an editorially
meaningful moment (creation, manual save, workflow event, rollback). The
content is gzip-compressed in BYTEA; the ``content_sha256`` column stores
the SHA-256 of the *uncompressed* body so it can be reused by the
Milestone 2 fixity scheduler without re-hashing every blob.

See [`backend/alembic/versions/0072_document_versions.py`] for the full
column rationale and index strategy.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class VersionOrigin(str, enum.Enum):
    """Why a ``document_versions`` row was written.

    The enum drives both the dedup behaviour (``creation``-and-later auto
    snapshots are skipped when SHA-256 matches the previous row) and the
    public ``?version=N`` permalink (which only resolves when ``origin``
    is ``publication``).
    """

    creation = "creation"
    manual = "manual"
    submission = "submission"
    rejection = "rejection"
    publication = "publication"
    rollback = "rollback"


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "document_filename",
            "version_number",
            name="uq_doc_versions_collection_filename_version",
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
    # Monotonic per (collection_id, document_filename). The service layer
    # computes ``MAX(version_number)+1`` inside the same transaction that
    # holds the per-document advisory lock, so two concurrent writers cannot
    # collide on the same (collection, filename, version_number) tuple.
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full XML body, gzip-compressed. Decompression happens in the service
    # layer; routers never see raw bytes.
    xml_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # SHA-256 of the *uncompressed* body. Reused by the M2 fixity scheduler.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Uncompressed size, kept for quick "show storage cost" reports without
    # decompressing every row.
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    origin: Mapped[VersionOrigin] = mapped_column(
        SAEnum(VersionOrigin, name="version_origin", create_type=False),
        nullable=False,
    )
    # Required by the service layer for ``manual`` origin; nullable for the
    # auto origins where the audit_log entry already records the why.
    message: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Back-pointer to the audit_log row that originated this version.
    # ``audit_log.id`` is BigInteger, not UUID — the FK type matches.
    audit_log_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("audit_log.id", ondelete="SET NULL"),
        nullable=True,
    )
