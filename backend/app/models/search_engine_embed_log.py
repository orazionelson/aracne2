"""SQLAlchemy ORM model for search engine embed request logs."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class SearchEngineEmbedLog(Base):
    """Log of search requests arriving via the embed widget.

    Records origin, IP, query, and whether the origin was whitelisted.
    Used for tracking which external sites are using the embed widget.
    """

    __tablename__ = "search_engine_embed_logs"
    __table_args__ = (
        sa.Index(
            "ix_embed_log_engine_time",
            "search_engine_id",
            "requested_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger(), primary_key=True, autoincrement=True)
    search_engine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_engines.id", ondelete="CASCADE"),
        nullable=False,
    )
    # HTTP Origin header sent by the browser (e.g. "https://example.com").
    origin: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # HTTP Referer header (full URL of the embedding page).
    referer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Client IP address (from X-Forwarded-For or direct connection).
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # Search query string.
    query: Mapped[str] = mapped_column(String(512), nullable=False)
    # "simple" or "advanced".
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # True when the origin was in the engine's whitelist (or the list is empty).
    allowed: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )
