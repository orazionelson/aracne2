"""End-to-end archive orchestration.

``archive_collection`` is the single entry point — it submits a URL to
SPN2, then polls its status for up to ~60 seconds (the value the user
pinned during design). If the capture has not completed in that
window, the record is left in ``pending`` state and the admin / EiC
can call ``refresh_status`` later to re-poll.

Per-collection state lives in ``plugin_data`` under the entity type
``collection`` and the key ``archive`` — same namespace convention used
by the Zenodo deposit plugin.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.plugins.internet_archive.config import (
    IARuntimeConfig,
    load_runtime_config,
)
from app.plugins.internet_archive.service import (
    IAError,
    InternetArchiveClient,
    StatusResult,
)
from app.services.plugin_data import PluginDataService

logger = structlog.get_logger()

PLUGIN_ID = "internet_archive"
ARCHIVE_KEY = "archive"

# 60-second budget split into 12 × 5s polls — matches the design pin
# ("Timeout 60 sec refresh"). If SPN2 has not returned by the end we
# leave the record ``pending`` and expose a refresh endpoint.
_POLL_MAX_SECONDS = 60
_POLL_INTERVAL_SECONDS = 5


class ArchiveSkipped(RuntimeError):
    """Raised when the plugin decides not to archive (missing keys, already
    archived, auto_archive=false, …). Not an error."""


async def _plugin_id(db: AsyncSession) -> uuid.UUID:
    """Resolve the Plugin row UUID for this plugin slug."""
    from sqlalchemy import select

    from app.models.plugin import Plugin

    row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if row is None:
        raise ArchiveSkipped(
            f"Plugin registry row '{PLUGIN_ID}' not found — has the loader run?"
        )
    return row.id


async def _already_archived(
    plugin_uuid: uuid.UUID, db: AsyncSession, collection_id: uuid.UUID
) -> bool:
    """Return True if a successful or still-pending record already exists.

    Failed records do NOT count — a retry on failure is the whole point
    of the refresh / manual archive endpoints.
    """
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="collection", key=ARCHIVE_KEY, entity_id=collection_id
    )
    if not existing:
        return False
    return existing.get("status") in {"success", "pending"}


async def _record(
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
        key=ARCHIVE_KEY,
        data=data,
        entity_id=collection_id,
    )
    await db.commit()


def _collection_url(cfg: IARuntimeConfig, slug: str) -> str:
    base = cfg.public_base_url.rstrip("/")
    return f"{base}/browse/{slug}"


async def _poll_until_terminal(
    client: InternetArchiveClient,
    job_id: str,
    *,
    sleep: Any = asyncio.sleep,
) -> StatusResult:
    """Poll *job_id* every 5s for up to 60s.

    Returns the first non-``pending`` result, or the last ``pending``
    result when the budget is exhausted. ``sleep`` is injected so tests
    can short-circuit the wait without patching the module globally.
    """
    last: StatusResult | None = None
    attempts = _POLL_MAX_SECONDS // _POLL_INTERVAL_SECONDS
    for attempt in range(attempts):
        if attempt > 0:
            await sleep(_POLL_INTERVAL_SECONDS)
        try:
            result = await client.status(job_id)
        except IAError as exc:
            # A transient error on a poll shouldn't abort the job — keep
            # trying for the remainder of the budget.
            logger.warning("ia_poll_error", job_id=job_id, error=str(exc))
            continue
        last = result
        if result.status != "pending":
            return result
    return last or StatusResult(
        status="pending",
        timestamp=None,
        original_url=None,
        wayback_url=None,
        error=None,
    )


async def archive_collection(
    db: AsyncSession,
    collection: Collection,
    *,
    ia_client: InternetArchiveClient | None = None,
    force: bool = False,
    sleep: Any = asyncio.sleep,
) -> dict[str, Any]:
    """Submit *collection*'s public URL to SPN2 and record the outcome.

    Returns the plugin_data payload that was written (or would have been
    written if the caller wants to inspect state without another fetch).
    Raises :class:`ArchiveSkipped` when preconditions are not met and
    :class:`IAError` on unrecoverable SPN2 / transport failures.
    """
    cfg = await load_runtime_config(db)
    if not cfg.credentials_set:
        raise ArchiveSkipped("Internet Archive API keys not configured")
    if not cfg.public_base_url:
        raise ArchiveSkipped("public_base_url setting is empty")

    plugin_uuid = await _plugin_id(db)

    if not force and await _already_archived(plugin_uuid, db, collection.id):
        raise ArchiveSkipped(
            f"Collection {collection.slug} already archived (no force)"
        )

    url = _collection_url(cfg, collection.slug)
    client = ia_client or InternetArchiveClient(
        access_key=cfg.access_key, secret_key=cfg.secret_key
    )

    submitted_at = datetime.now(UTC).isoformat()

    try:
        submit = await client.submit(url)
    except IAError as exc:
        data = {
            "status": "failed",
            "original_url": url,
            "submitted_at": submitted_at,
            "error": str(exc),
            "http_status": exc.status_code,
        }
        await _record(plugin_uuid=plugin_uuid, db=db, collection_id=collection.id, data=data)
        raise

    # Write a pending record immediately so the UI has something to show
    # even if the backend crashes mid-poll.
    await _record(
        plugin_uuid=plugin_uuid,
        db=db,
        collection_id=collection.id,
        data={
            "status": "pending",
            "job_id": submit.job_id,
            "original_url": submit.url,
            "submitted_at": submitted_at,
            "error": None,
        },
    )

    result = await _poll_until_terminal(client, submit.job_id, sleep=sleep)
    data = {
        "status": result.status,
        "job_id": submit.job_id,
        "original_url": result.original_url or submit.url,
        "wayback_url": result.wayback_url,
        "timestamp": result.timestamp,
        "submitted_at": submitted_at,
        "error": result.error,
    }
    await _record(plugin_uuid=plugin_uuid, db=db, collection_id=collection.id, data=data)
    return data


async def refresh_status(
    db: AsyncSession,
    collection: Collection,
    *,
    ia_client: InternetArchiveClient | None = None,
    sleep: Any = asyncio.sleep,
) -> dict[str, Any]:
    """Re-poll a previously submitted pending job.

    Does nothing and surfaces the current record if the collection's
    archive is already terminal (success or failed), since SPN2 does not
    re-open completed jobs.
    """
    plugin_uuid = await _plugin_id(db)
    svc = PluginDataService(plugin_id=plugin_uuid)
    existing = await svc.get(
        db, entity_type="collection", key=ARCHIVE_KEY, entity_id=collection.id
    )
    if not existing:
        raise ArchiveSkipped("No archive record to refresh")
    if existing.get("status") != "pending":
        # Nothing to refresh — return the existing terminal record.
        return existing
    job_id = existing.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ArchiveSkipped("Existing record has no job_id")

    cfg = await load_runtime_config(db)
    if not cfg.credentials_set:
        raise ArchiveSkipped("Internet Archive API keys not configured")

    client = ia_client or InternetArchiveClient(
        access_key=cfg.access_key, secret_key=cfg.secret_key
    )
    result = await _poll_until_terminal(client, job_id, sleep=sleep)
    data = {
        **existing,
        "status": result.status,
        "original_url": result.original_url or existing.get("original_url"),
        "wayback_url": result.wayback_url,
        "timestamp": result.timestamp,
        "error": result.error,
    }
    await _record(plugin_uuid=plugin_uuid, db=db, collection_id=collection.id, data=data)
    return data


# ── Hook handler ────────────────────────────────────────────────────────────


async def on_collection_published(collection: Collection, **_: object) -> None:
    """Fire-and-forget archive when auto_archive is on."""
    from app.db.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cfg = await load_runtime_config(db)
        if not cfg.auto_archive:
            logger.info(
                "ia_archive_skipped",
                collection_id=str(collection.id),
                slug=collection.slug,
                reason="auto_archive is off",
            )
            return
        try:
            data = await archive_collection(db, collection)
        except ArchiveSkipped as exc:
            logger.info(
                "ia_archive_skipped",
                collection_id=str(collection.id),
                slug=collection.slug,
                reason=str(exc),
            )
            return
        except IAError as exc:
            logger.warning(
                "ia_archive_failed",
                collection_id=str(collection.id),
                slug=collection.slug,
                error=str(exc),
                status_code=exc.status_code,
            )
            return
        logger.info(
            "ia_archive_recorded",
            collection_id=str(collection.id),
            slug=collection.slug,
            status=data["status"],
            wayback_url=data.get("wayback_url"),
        )


__all__ = [
    "ARCHIVE_KEY",
    "PLUGIN_ID",
    "ArchiveSkipped",
    "archive_collection",
    "on_collection_published",
    "refresh_status",
]
