"""
plugin_data — generic key-value store for plugin-owned data.

Usage inside a plugin:

    from app.services.plugin_data import PluginDataService

    svc = PluginDataService(plugin_id=my_plugin_uuid)

    # Store a value (insert or update)
    await svc.set(db, entity_type="collection", key="counter", data={"n": 42},
                  entity_id=some_uuid)

    # Read it back
    payload = await svc.get(db, entity_type="collection", key="counter",
                            entity_id=some_uuid)

    # List all keys in a namespace
    keys = await svc.list_keys(db, entity_type="collection", entity_id=some_uuid)

    # Delete a single entry
    await svc.delete(db, entity_type="collection", key="counter",
                     entity_id=some_uuid)

    # Wipe all data owned by this plugin (e.g. on uninstall)
    count = await svc.delete_all(db)

The namespace is (plugin_id, entity_type, entity_id, key).
entity_id=None addresses plugin-global data (not tied to any platform entity).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plugin_data import PluginData


def _now() -> datetime:
    return datetime.now(UTC)


def _where(
    plugin_id: uuid.UUID,
    entity_type: str,
    key: str,
    entity_id: uuid.UUID | None,
):
    """Return the SQLAlchemy WHERE clause that identifies a single row."""
    clause = (
        (PluginData.plugin_id == plugin_id)
        & (PluginData.entity_type == entity_type)
        & (PluginData.key == key)
    )
    if entity_id is None:
        clause &= PluginData.entity_id.is_(None)
    else:
        clause &= (PluginData.entity_id == entity_id)
    return clause


class PluginDataService:
    """Scoped service for a single plugin's data namespace."""

    def __init__(self, plugin_id: uuid.UUID) -> None:
        self._plugin_id = plugin_id

    # ── Core operations ────────────────────────────────────────────────────────

    async def get(
        self,
        db: AsyncSession,
        entity_type: str,
        key: str,
        entity_id: uuid.UUID | None = None,
    ) -> dict[str, object] | None:
        """Return the stored JSONB payload, or None if the key does not exist."""
        row = await db.scalar(
            select(PluginData).where(
                _where(self._plugin_id, entity_type, key, entity_id)
            )
        )
        return row.data if row else None

    async def set(
        self,
        db: AsyncSession,
        entity_type: str,
        key: str,
        data: dict[str, object],
        entity_id: uuid.UUID | None = None,
    ) -> PluginData:
        """Insert or update a key.  Returns the persisted row (flushed, not committed)."""
        row = await db.scalar(
            select(PluginData).where(
                _where(self._plugin_id, entity_type, key, entity_id)
            )
        )
        if row:
            row.data = data
            row.updated_at = _now()
        else:
            row = PluginData(
                plugin_id=self._plugin_id,
                entity_type=entity_type,
                entity_id=entity_id,
                key=key,
                data=data,
            )
            db.add(row)
        await db.flush()
        return row

    async def delete(
        self,
        db: AsyncSession,
        entity_type: str,
        key: str,
        entity_id: uuid.UUID | None = None,
    ) -> bool:
        """Delete a single key.  Returns True if a row was removed, False if not found."""
        row = await db.scalar(
            select(PluginData).where(
                _where(self._plugin_id, entity_type, key, entity_id)
            )
        )
        if not row:
            return False
        await db.delete(row)
        await db.flush()
        return True

    # ── Bulk operations ────────────────────────────────────────────────────────

    async def list_keys(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
    ) -> list[str]:
        """Return all keys stored under (plugin, entity_type, entity_id)."""
        clause = (PluginData.plugin_id == self._plugin_id) & (
            PluginData.entity_type == entity_type
        )
        if entity_id is None:
            clause &= PluginData.entity_id.is_(None)
        else:
            clause &= PluginData.entity_id == entity_id

        rows = list(await db.scalars(select(PluginData.key).where(clause)))
        return rows

    async def list_all(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
    ) -> list[PluginData]:
        """Return all PluginData rows under (plugin, entity_type, entity_id)."""
        clause = (PluginData.plugin_id == self._plugin_id) & (
            PluginData.entity_type == entity_type
        )
        if entity_id is None:
            clause &= PluginData.entity_id.is_(None)
        else:
            clause &= PluginData.entity_id == entity_id

        return list(await db.scalars(select(PluginData).where(clause)))

    async def delete_all(self, db: AsyncSession) -> int:
        """Delete every row owned by this plugin.

        Returns the number of deleted rows.
        Intended for plugin uninstall / cleanup hooks.
        """
        result = await db.execute(
            delete(PluginData).where(PluginData.plugin_id == self._plugin_id)
        )
        await db.flush()
        return result.rowcount
