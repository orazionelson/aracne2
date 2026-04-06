"""
PluginLoader — discovers, syncs and mounts Aracne2 plugins.

Lifecycle (called once in the FastAPI lifespan startup):
  1. discover()        — scan filesystem for PluginBase subclasses
  2. sync_registry()   — upsert Plugin rows in PostgreSQL
  3. load_active()     — mount routers for active plugins on the FastAPI app

Native plugins (meta.native=True) are always active and are mounted
regardless of their DB status.  Non-native plugins are mounted only when
Plugin.status == PluginStatus.active.

Changes to activation status take effect after the next server restart.
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
        for plugin_id, cls in self._discovered.items():
            meta = cls.meta
            prefix = "_native." if meta.native else ""
            entry_point = f"app.plugins.{prefix}{plugin_id}.plugin"
            now = datetime.now(UTC)

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
                        status=(
                            PluginStatus.active
                            if meta.native
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
                if cls.router.routes:
                    app.include_router(cls.router, prefix="/api/v1")
                logger.info(
                    "plugin_loaded", id=plugin_id, native=cls.meta.native
                )

    # ── Public helpers ────────────────────────────────────────────────────────

    def get_class(self, plugin_id: str) -> type[PluginBase] | None:
        """Return the PluginBase subclass for *plugin_id*, or None."""
        return self._discovered.get(plugin_id)


plugin_loader = PluginLoader()
