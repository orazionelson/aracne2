from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.models.plugin import Plugin, PluginStatus
from app.schemas.plugins import PluginResponse


async def list_plugins(db: AsyncSession) -> list[PluginResponse]:
    """Return all registered plugins ordered by native-first, then name."""
    rows = await db.scalars(
        select(Plugin).order_by(Plugin.is_native.desc(), Plugin.name)
    )
    return [PluginResponse.model_validate(r) for r in rows]


async def _get_or_404(db: AsyncSession, name: str) -> Plugin:
    row = await db.scalar(select(Plugin).where(Plugin.name == name))
    if not row:
        raise NotFoundError(f"Plugin '{name}' not found")
    return row


async def activate_plugin(db: AsyncSession, name: str) -> PluginResponse:
    """Set a non-native plugin's status to active."""
    plugin = await _get_or_404(db, name)
    if plugin.is_native:
        raise ConflictError("Native plugins are always active and cannot be toggled")
    if plugin.status == PluginStatus.active:
        raise ConflictError(f"Plugin '{name}' is already active")
    plugin.status = PluginStatus.active
    plugin.updated_at = datetime.now(UTC)
    await db.flush()
    return PluginResponse.model_validate(plugin)


async def deactivate_plugin(db: AsyncSession, name: str) -> PluginResponse:
    """Set a non-native plugin's status to inactive."""
    plugin = await _get_or_404(db, name)
    if plugin.is_native:
        raise AuthorizationError("Native plugins cannot be deactivated")
    if plugin.status == PluginStatus.inactive:
        raise ConflictError(f"Plugin '{name}' is already inactive")
    plugin.status = PluginStatus.inactive
    plugin.updated_at = datetime.now(UTC)
    await db.flush()
    return PluginResponse.model_validate(plugin)


async def delete_plugin(db: AsyncSession, name: str) -> None:
    """Delete a non-native plugin record. Plugin must be inactive first."""
    plugin = await _get_or_404(db, name)
    if plugin.is_native:
        raise AuthorizationError("Native plugins cannot be deleted")
    if plugin.status == PluginStatus.active:
        raise ConflictError(
            f"Deactivate plugin '{name}' before deleting it"
        )
    await db.delete(plugin)
    await db.flush()
