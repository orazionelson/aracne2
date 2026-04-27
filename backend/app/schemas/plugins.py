import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.plugin import PluginStatus


class PluginResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    version: str | None
    description: str | None
    author: str | None
    entry_point: str | None
    is_native: bool
    status: PluginStatus
    # UI auto-cabling contract — see app/core/plugin_base.py.
    capabilities: list[str]
    ui_descriptor: dict[str, object] | None
    installed_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
