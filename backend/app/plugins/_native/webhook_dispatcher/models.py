"""SQLAlchemy model for webhook endpoint configuration."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base
from app.db.types import JsonbType


def _now() -> datetime:
    return datetime.now(UTC)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # List of event names this endpoint subscribes to — stored as JSONB array
    # on PostgreSQL; JSON on SQLite (tests) via the JsonbType TypeDecorator.
    events: Mapped[list] = mapped_column(JsonbType, nullable=False, default=list)
    # Shared secret for HMAC-SHA256 request signing (optional).
    # Stored in plaintext — Admin-only access, no public exposure.
    secret: Mapped[str | None] = mapped_column(String(256), nullable=True, default=None)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="TRUE"
    )
    # Last delivery metadata
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
