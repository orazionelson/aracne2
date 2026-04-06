import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base
from app.db.types import JsonbType


def _now() -> datetime:
    return datetime.now(UTC)


class PluginData(Base):
    """Generic key-value store for non-native plugins.

    Namespace: (plugin_id, entity_type, entity_id, key).

    - plugin_id   — owning plugin (CASCADE DELETE on plugin removal)
    - entity_type — logical category, e.g. "collection", "document", "global"
    - entity_id   — UUID of the related platform entity; NULL for plugin-global data
    - key         — string key within the namespace
    - data        — free-form JSONB payload

    Uniqueness is enforced by two partial indexes that handle the NULL entity_id case
    correctly (PostgreSQL treats NULL != NULL in standard UNIQUE constraints).
    """

    __tablename__ = "plugin_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plugins.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, default=None
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(
        JsonbType, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        # Lookup index covering the full namespace
        Index(
            "ix_plugin_data_namespace",
            "plugin_id",
            "entity_type",
            "entity_id",
            "key",
        ),
    )
