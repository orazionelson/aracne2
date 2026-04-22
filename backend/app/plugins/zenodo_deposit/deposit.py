"""End-to-end deposit orchestration.

``deposit_collection`` is the single entry point — call it from the hook
handler or from the manual re-deposit endpoint.  It reads config from
``system_settings``, fetches the collection's documents from eXist-db,
pushes them to Zenodo, and records the outcome in ``plugin_data`` so
the UI can surface a DOI badge next to the collection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, existdb_client
from app.models.collection import Collection
from app.models.license import License
from app.plugins.zenodo_deposit.config import ZenodoRuntimeConfig, load_runtime_config
from app.plugins.zenodo_deposit.mapping import (
    collection_to_metadata,
    to_zenodo_payload,
)
from app.plugins.zenodo_deposit.service import DepositResult, ZenodoClient, ZenodoError
from app.services.plugin_data import PluginDataService

logger = structlog.get_logger()

# The plugin slug used both as the ``Plugin.name`` DB value and as the
# ``entity_type`` namespace in ``plugin_data``.
PLUGIN_ID = "zenodo_deposit"

# Per-collection plugin_data key — most recent deposit record for this plugin.
DEPOSIT_KEY = "deposit"


class DepositSkipped(RuntimeError):
    """Raised when the plugin decides not to deposit (missing token, already
    deposited, …).  Not an error — the hook swallows it silently."""


async def _load_license(db: AsyncSession, col: Collection) -> License | None:
    if col.license_id is None:
        return None
    return await db.get(License, col.license_id)


async def _load_files(
    existdb: ExistDBClient, slug: str
) -> list[tuple[str, bytes]]:
    """Return the list of ``(filename, xml_bytes)`` for all docs in *slug*."""
    names = await existdb.list_collection(slug)
    files: list[tuple[str, bytes]] = []
    for name in names:
        try:
            content = await existdb.get_document(slug, name)
        except Exception as exc:  # noqa: BLE001 — one missing doc shouldn't nuke deposit
            logger.warning("zenodo_file_fetch_failed", filename=name, error=str(exc))
            continue
        files.append((name, content))
    return files


async def _plugin_id(db: AsyncSession) -> uuid.UUID:
    """Resolve the Plugin row UUID for this plugin slug.

    The plugin loader inserts this row on every startup, so absence is a
    programmer error (plugin code running before the loader ran).
    """
    from sqlalchemy import select

    from app.models.plugin import Plugin

    row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if row is None:
        raise DepositSkipped(
            f"Plugin registry row '{PLUGIN_ID}' not found — has the loader run?"
        )
    return row.id


async def _already_deposited(
    plugin_uuid: uuid.UUID, db: AsyncSession, collection_id: uuid.UUID
) -> bool:
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="collection", key=DEPOSIT_KEY, entity_id=collection_id
    )
    if not existing:
        return False
    # Re-deposit after a failed attempt — but not after a successful one.
    status = existing.get("status")
    return status in {"draft", "published"}


async def _record_status(
    *,
    plugin_uuid: uuid.UUID,
    db: AsyncSession,
    collection_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    svc = PluginDataService(plugin_id=plugin_uuid)
    await svc.set(
        db,
        entity_type="collection",
        key=DEPOSIT_KEY,
        data=data,
        entity_id=collection_id,
    )
    await db.commit()


async def deposit_collection(
    db: AsyncSession,
    collection: Collection,
    *,
    existdb: ExistDBClient | None = None,
    zenodo_client: ZenodoClient | None = None,
    force: bool = False,
) -> DepositResult:
    """Deposit *collection* on Zenodo.

    Call with ``force=True`` from the manual re-deposit endpoint to
    ignore an existing successful record; the automatic hook path leaves
    force at its default (False).
    """
    cfg = await load_runtime_config(db)
    if not cfg.api_token:
        raise DepositSkipped("Zenodo API token not configured")

    plugin_uuid = await _plugin_id(db)

    if not force and await _already_deposited(plugin_uuid, db, collection.id):
        raise DepositSkipped(
            f"Collection {collection.slug} already deposited (no force)"
        )

    license_obj = await _load_license(db, collection)
    meta = collection_to_metadata(
        collection=collection,
        license_obj=license_obj,
        public_base_url=cfg.public_base_url,
        publication_type=cfg.publication_type,
        access_right=cfg.access_right,
    )
    payload = to_zenodo_payload(meta, community=cfg.default_community or None)

    files = await _load_files(existdb or existdb_client, collection.slug)

    client = zenodo_client or ZenodoClient(
        base_url=cfg.base_url, api_token=cfg.api_token
    )

    try:
        draft = await client.create_draft()
        for filename, content in files:
            await client.upload_file(draft.bucket_url, filename, content)
        await client.update_metadata(draft.id, payload)

        if cfg.auto_publish:
            result = await client.publish(draft.id)
        else:
            result = DepositResult(
                id=draft.id,
                doi=None,
                record_url=draft.record_url,
                status="draft",
            )
    except ZenodoError as exc:
        await _record_status(
            plugin_uuid=plugin_uuid,
            db=db,
            collection_id=collection.id,
            data={
                "status": "failed",
                "error": str(exc),
                "http_status": exc.status_code,
                "submitted_at": datetime.now(UTC).isoformat(),
            },
        )
        raise

    await _record_status(
        plugin_uuid=plugin_uuid,
        db=db,
        collection_id=collection.id,
        data={
            "status": result.status,
            "deposit_id": result.id,
            "doi": result.doi,
            "record_url": result.record_url,
            "submitted_at": datetime.now(UTC).isoformat(),
            "error": None,
        },
    )
    return result


# ── Hook handler ────────────────────────────────────────────────────────────

async def on_collection_published(collection: Collection, **_: object) -> None:
    """Fire-and-forget: run a deposit in a fresh session, never block publish."""
    from app.db.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            result = await deposit_collection(db, collection)
        except DepositSkipped as exc:
            logger.info(
                "zenodo_deposit_skipped",
                collection_id=str(collection.id),
                slug=collection.slug,
                reason=str(exc),
            )
            return
        except ZenodoError as exc:
            logger.warning(
                "zenodo_deposit_failed",
                collection_id=str(collection.id),
                slug=collection.slug,
                error=str(exc),
                status_code=exc.status_code,
            )
            return
        logger.info(
            "zenodo_deposit_recorded",
            collection_id=str(collection.id),
            slug=collection.slug,
            deposit_id=result.id,
            doi=result.doi,
            status=result.status,
        )


__all__ = [
    "DEPOSIT_KEY",
    "PLUGIN_ID",
    "DepositSkipped",
    "ZenodoRuntimeConfig",
    "deposit_collection",
    "on_collection_published",
]
