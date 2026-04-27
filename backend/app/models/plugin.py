import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base
from app.db.types import JsonbType


def _now() -> datetime:
    return datetime.now(UTC)


class PluginStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str | None] = mapped_column(String(32), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    author: Mapped[str | None] = mapped_column(String(256), default=None)
    entry_point: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[PluginStatus] = mapped_column(
        SAEnum(PluginStatus, name="plugin_status", create_type=False),
        nullable=False,
        default=PluginStatus.inactive,
    )
    config: Mapped[dict[str, object]] = mapped_column(JsonbType, nullable=False, default=dict)
    hooks: Mapped[list[object]] = mapped_column(JsonbType, nullable=False, default=list)
    # Capabilities the plugin advertises to the SPA, keyed by tag (e.g.
    # ``inline_authority``). Mirrors PluginMeta.capabilities.
    capabilities: Mapped[list[str]] = mapped_column(
        JsonbType, nullable=False, default=list, server_default="[]"
    )
    # Per-capability UI metadata the SPA reads to auto-cable the plugin
    # into the right toolbar / panel. Mirrors PluginMeta.ui_descriptor.
    ui_descriptor: Mapped[dict[str, object] | None] = mapped_column(
        JsonbType, nullable=True, default=None
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    is_native: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="FALSE"
    )
    installed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
