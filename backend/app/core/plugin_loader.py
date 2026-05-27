"""
PluginLoader — discovers, syncs and mounts Aracne2 plugins.

Startup (called once in the FastAPI lifespan):
  1. discover()        — scan filesystem for PluginBase subclasses
  2. sync_registry()   — upsert Plugin rows in PostgreSQL
  3. load_active()     — mount routers for active plugins on the FastAPI app

Runtime activation / deactivation:
  • mount_plugin(app, plugin_id)   — append the plugin's router to the
    live ASGI app and remember the appended Route objects.
  • unmount_plugin(app, plugin_id) — pop those Route objects off so the
    URL space goes back to 404 for that plugin.

Both are called by the ``/plugins/{name}/activate`` and
``/plugins/{name}/deactivate`` endpoints, so toggling a plugin in the
admin UI takes effect immediately — no backend restart required.

Native plugins (meta.native=True) are always active and are mounted at
startup regardless of their DB status.
"""

import importlib
import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plugin_base import PluginBase
from app.models.plugin import Plugin, PluginStatus

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()

# app/plugins/ — sibling of app/core/
_PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


class PluginLoader:
    def __init__(self) -> None:
        self._discovered: dict[str, type[PluginBase]] = {}
        # plugin_id → list of Route objects that ``app.include_router``
        # appended on the running ASGI app. Populated at startup
        # (``load_active``) and at every runtime activation
        # (``mount_plugin``); consumed by ``unmount_plugin`` to remove
        # the exact same Route instances on deactivation, so toggling
        # a plugin in the admin UI does not require a backend
        # restart anymore.
        self._mounted_routes: dict[str, list[object]] = {}

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover(self) -> None:
        """Scan _native/ and top-level of plugins/ for PluginBase subclasses."""
        self._discovered.clear()

        # Native plugins: plugins/_native/<slug>/plugin.py
        native_dir = _PLUGINS_DIR / "_native"
        if native_dir.is_dir():
            for entry in sorted(native_dir.iterdir()):
                if entry.is_dir() and not entry.name.startswith("_"):
                    self._import_plugin(
                        f"app.plugins._native.{entry.name}", expected_native=True
                    )

        # Non-native plugins: plugins/<slug>/plugin.py (skip _-prefixed dirs)
        for entry in sorted(_PLUGINS_DIR.iterdir()):
            if entry.is_dir() and not entry.name.startswith("_"):
                self._import_plugin(
                    f"app.plugins.{entry.name}", expected_native=False
                )

    def _import_plugin(self, module_path: str, *, expected_native: bool) -> None:
        try:
            module = importlib.import_module(f"{module_path}.plugin")
        except ModuleNotFoundError:
            logger.warning("plugin_module_not_found", module=module_path)
            return
        except Exception as exc:
            logger.error("plugin_import_error", module=module_path, error=str(exc))
            return

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, PluginBase) and obj is not PluginBase:
                if obj.meta.native != expected_native:
                    logger.warning(
                        "plugin_native_mismatch",
                        module=module_path,
                        expected=expected_native,
                        got=obj.meta.native,
                    )
                self._discovered[obj.meta.id] = obj
                logger.info(
                    "plugin_discovered", id=obj.meta.id, native=obj.meta.native
                )
                return

        logger.warning("plugin_no_class_found", module=module_path)

    # ── DB sync ───────────────────────────────────────────────────────────────

    async def sync_registry(self, db: AsyncSession) -> None:
        """Upsert a Plugin row in PostgreSQL for every discovered plugin."""
        from app.models.system_setting import SystemSetting

        for plugin_id, cls in self._discovered.items():
            meta = cls.meta
            prefix = "_native." if meta.native else ""
            entry_point = f"app.plugins.{prefix}{plugin_id}.plugin"
            now = datetime.now(UTC)

            # Idempotent toggle row for plugins that advertise the
            # public_navigation capability — covers natives (always
            # active, never go through activate_plugin) as well as
            # the boot of a deployment whose plugin landed pre-toggle.
            desc = meta.ui_descriptor or {}
            if isinstance(desc, dict) and "public_navigation" in desc:
                toggle_key = f"public_link_{plugin_id}_enabled"
                existing_toggle = await db.get(SystemSetting, toggle_key)
                if existing_toggle is None:
                    db.add(
                        SystemSetting(
                            key=toggle_key,
                            value="false",
                            type="bool",
                            description=(
                                f"Show {meta.name} in the public navigation."
                            ),
                        )
                    )

            existing = await db.scalar(
                select(Plugin).where(Plugin.name == plugin_id)
            )
            if existing:
                existing.display_name = meta.name
                existing.version = meta.version
                existing.description = meta.description
                existing.author = meta.author
                existing.is_native = meta.native
                existing.entry_point = entry_point
                existing.capabilities = list(meta.capabilities)
                existing.ui_descriptor = meta.ui_descriptor
                existing.updated_at = now
                # Native plugins are always forced active in the registry.
                if meta.native:
                    existing.status = PluginStatus.active
            else:
                db.add(
                    Plugin(
                        name=plugin_id,
                        display_name=meta.name,
                        version=meta.version,
                        description=meta.description,
                        author=meta.author,
                        is_native=meta.native,
                        entry_point=entry_point,
                        capabilities=list(meta.capabilities),
                        ui_descriptor=meta.ui_descriptor,
                        # New row: native ⇒ always active; non-native ⇒
                        # honour ``meta.default_active`` so a plugin can
                        # opt into being live from first boot (e.g. Help).
                        # Existing rows are never touched here — Admin
                        # decisions persist across reboots.
                        status=(
                            PluginStatus.active
                            if meta.native or meta.default_active
                            else PluginStatus.inactive
                        ),
                    )
                )

        await db.flush()
        logger.info("plugin_registry_synced", count=len(self._discovered))

    # ── Router mounting ───────────────────────────────────────────────────────

    async def load_active(self, app: "FastAPI", db: AsyncSession) -> None:
        """Discover plugins, sync the registry, then mount active routers."""
        self.discover()
        await self.sync_registry(db)
        await db.commit()

        for plugin_id, cls in self._discovered.items():
            row = await db.scalar(
                select(Plugin).where(Plugin.name == plugin_id)
            )
            if row and row.status == PluginStatus.active:
                self._mount(app, plugin_id, cls)

    # ── Runtime mount / unmount ───────────────────────────────────────────────

    def _mount(
        self, app: "FastAPI", plugin_id: str, cls: type[PluginBase]
    ) -> None:
        """Append the plugin's router to the running ASGI app and remember
        which Route objects came from us, so we can pop them later."""
        if not cls.router.routes:
            return
        if plugin_id in self._mounted_routes:
            # Already mounted — guard against accidental double-mounts.
            return
        before = set(id(r) for r in app.router.routes)
        app.include_router(cls.router, prefix="/api/v1")
        added = [r for r in app.router.routes if id(r) not in before]
        self._mounted_routes[plugin_id] = added
        # OpenAPI schema is cached after the first /docs hit; invalidate
        # so the new routes show up the next time someone opens it.
        app.openapi_schema = None
        logger.info(
            "plugin_loaded",
            id=plugin_id,
            native=cls.meta.native,
            route_count=len(added),
        )

    def mount_plugin(self, app: "FastAPI", plugin_id: str) -> bool:
        """Hot-mount a plugin's router on the live FastAPI app.

        Called by the admin "activate" endpoint after the DB row has
        been flipped, so the new routes start serving requests
        immediately — no backend restart required. Returns ``True`` on
        success, ``False`` if the plugin id is unknown, has no router
        defined, or is already mounted.
        """
        cls = self._discovered.get(plugin_id)
        if cls is None:
            return False
        if plugin_id in self._mounted_routes:
            return False  # already serving — nothing to do
        if not cls.router.routes:
            return False  # plugin has no HTTP surface (hook-only)
        self._mount(app, plugin_id, cls)
        return True

    def unmount_plugin(self, app: "FastAPI", plugin_id: str) -> bool:
        """Remove a plugin's routes from the live FastAPI app.

        Called by the admin "deactivate" endpoint. Returns ``True`` on
        success, ``False`` if no routes were tracked for that plugin
        (e.g. it was never active in this process). Native plugins
        should not be deactivatable in the first place — the caller
        guards on ``meta.native`` before invoking this.
        """
        routes = self._mounted_routes.pop(plugin_id, None)
        if not routes:
            return False
        # ``app.router.routes`` is a regular Python list — remove every
        # tracked instance. Use identity comparison via ``is`` to
        # survive any ``__eq__`` overrides on Route subclasses.
        kept = [r for r in app.router.routes if all(r is not x for x in routes)]
        app.router.routes[:] = kept
        app.openapi_schema = None
        logger.info(
            "plugin_unloaded", id=plugin_id, route_count=len(routes)
        )
        return True

    # ── Public helpers ────────────────────────────────────────────────────────

    def get_class(self, plugin_id: str) -> type[PluginBase] | None:
        """Return the PluginBase subclass for *plugin_id*, or None."""
        return self._discovered.get(plugin_id)


plugin_loader = PluginLoader()
