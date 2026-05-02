from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from app.models.plugin import Plugin, PluginStatus
from app.models.system_setting import SystemSetting
from app.schemas.plugins import PluginResponse


def _public_link_setting_key(plugin_name: str) -> str:
    """Mirror of ``services.settings.public_link_setting_key``.

    Duplicated here to avoid the circular import services.settings →
    services.plugins; the format is part of the platform contract and
    rarely changes.
    """
    return f"public_link_{plugin_name}_enabled"


async def _ensure_public_link_toggle(db: AsyncSession, plugin: Plugin) -> None:
    """Idempotently create the per-plugin public-link toggle row.

    Only relevant when the plugin advertises the ``public_navigation``
    capability. Default value is ``"false"`` so activating a plugin
    never auto-publishes its public link — the Admin must consciously
    flip the toggle from the Public Pages panel.
    """
    desc = plugin.ui_descriptor or {}
    if not isinstance(desc, dict) or "public_navigation" not in desc:
        return
    key = _public_link_setting_key(plugin.name)
    existing = await db.get(SystemSetting, key)
    if existing is not None:
        return
    db.add(
        SystemSetting(
            key=key,
            value="false",
            type="bool",
            description=(
                f"Show {plugin.display_name or plugin.name} in the public "
                f"navigation. Default off — flip on to surface the link."
            ),
        )
    )


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
    await _ensure_public_link_toggle(db, plugin)
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
