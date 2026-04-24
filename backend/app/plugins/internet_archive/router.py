"""Internet Archive plugin — admin + per-collection router.

Endpoints (all under ``/api/v1`` mount):

- ``GET  /plugins/internet-archive/config``                    → current config
- ``PUT  /plugins/internet-archive/config``                    → Admin-only update
- ``GET  /plugins/internet-archive/collections/{slug}/status`` → last record
- ``POST /plugins/internet-archive/collections/{slug}/archive`` → force a fresh capture
- ``POST /plugins/internet-archive/collections/{slug}/refresh`` → re-poll a pending job
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.collection import Collection
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins.internet_archive.archive import (
    ARCHIVE_KEY,
    PLUGIN_ID,
    WEBSITE_ARCHIVE_KEY,
    ArchiveSkipped,
    archive_collection,
    archive_website,
    refresh_status,
    refresh_website_status,
)
from app.plugins.internet_archive.config import (
    K_ACCESS_KEY,
    K_AUTO_ARCHIVE,
    K_SECRET_KEY,
    load_runtime_config,
)
from app.plugins.internet_archive.schemas import (
    ArchiveStatus,
    InternetArchiveConfigResponse,
    InternetArchiveConfigUpdate,
)
from app.plugins.internet_archive.service import IAError
from app.schemas.common import DataResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/plugins/internet-archive", tags=["internet-archive"])

_admin = Depends(require_role(min_role="Admin"))
_eic = Depends(require_role(min_role="EditorInChief"))


async def _write_setting(
    db: AsyncSession, key: str, value: str, actor: User
) -> None:
    stored = (
        encrypt_value(value, app_settings.jwt_secret)
        if key in SENSITIVE_KEYS
        else value
    )
    row = await db.get(SystemSetting, key)
    if row is None:
        raise HTTPException(
            status_code=500,
            detail=f"Setting '{key}' missing — did migration 0051 run?",
        )
    row.value = stored
    row.updated_by = actor.id
    await db.flush()


def _config_response(cfg: Any) -> InternetArchiveConfigResponse:
    return InternetArchiveConfigResponse(
        access_key_set=bool(cfg.access_key),
        secret_key_set=bool(cfg.secret_key),
        auto_archive=cfg.auto_archive,
    )


@router.get("/config")
async def get_config(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[InternetArchiveConfigResponse]:
    cfg = await load_runtime_config(db)
    return DataResponse(data=_config_response(cfg))


@router.put("/config")
async def update_config(
    body: InternetArchiveConfigUpdate,
    actor: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[InternetArchiveConfigResponse]:
    if body.access_key is not None:
        await _write_setting(db, K_ACCESS_KEY, body.access_key, actor)
    if body.secret_key is not None:
        await _write_setting(db, K_SECRET_KEY, body.secret_key, actor)
    if body.auto_archive is not None:
        await _write_setting(
            db, K_AUTO_ARCHIVE, "true" if body.auto_archive else "false", actor
        )
    await db.commit()
    cfg = await load_runtime_config(db)
    return DataResponse(data=_config_response(cfg))


async def _resolve_collection(db: AsyncSession, slug: str) -> Collection:
    col = await db.scalar(select(Collection).where(Collection.slug == slug))
    if col is None:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    return col


@router.get("/collections/{slug}/status")
async def get_archive_status(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ArchiveStatus | None]:
    """Return the most recent archive record for a collection, or ``null``."""
    from app.models.plugin import Plugin
    from app.services.plugin_data import PluginDataService

    col = await _resolve_collection(db, slug)
    plugin_row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if plugin_row is None:
        return DataResponse(data=None)
    svc = PluginDataService(plugin_id=plugin_row.id)
    data = await svc.get(
        db, entity_type="collection", key=ARCHIVE_KEY, entity_id=col.id
    )
    if data is None:
        return DataResponse(data=None)
    return DataResponse(data=ArchiveStatus.model_validate(data))


@router.post(
    "/collections/{slug}/archive",
    status_code=status.HTTP_202_ACCEPTED,
)
async def force_archive(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ArchiveStatus]:
    """Force a fresh archive attempt even if the collection is already archived."""
    col = await _resolve_collection(db, slug)
    try:
        data = await archive_collection(db, col, force=True)
    except ArchiveSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except IAError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Internet Archive submit failed: {exc}",
        )
    return DataResponse(
        data=ArchiveStatus.model_validate({
            "submitted_at": datetime.now(UTC),
            **data,
        })
    )


@router.post("/collections/{slug}/refresh")
async def refresh_archive(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ArchiveStatus]:
    """Re-poll a pending SPN2 job.

    Does nothing for records already in a terminal state — returns the
    existing record so the UI can refresh its view without branching.
    """
    col = await _resolve_collection(db, slug)
    try:
        data = await refresh_status(db, col)
    except ArchiveSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except IAError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Internet Archive status poll failed: {exc}",
        )
    return DataResponse(data=ArchiveStatus.model_validate(data))


# ── Per-website endpoints ───────────────────────────────────────────────────


async def _resolve_website(db: AsyncSession, slug: str):  # type: ignore[no-untyped-def]
    from app.models.website import Website

    row = await db.scalar(select(Website).where(Website.slug == slug))
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Website '{slug}' not found",
        )
    return row


@router.get("/websites/{slug}/status")
async def get_website_archive_status(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ArchiveStatus | None]:
    """Most recent website-archive record for *slug*, or ``null``."""
    from app.models.plugin import Plugin
    from app.services.plugin_data import PluginDataService

    website = await _resolve_website(db, slug)
    plugin_row = await db.scalar(
        select(Plugin).where(Plugin.name == PLUGIN_ID),
    )
    if plugin_row is None:
        return DataResponse(data=None)
    svc = PluginDataService(plugin_id=plugin_row.id)
    data = await svc.get(
        db, entity_type="website", key=WEBSITE_ARCHIVE_KEY,
        entity_id=website.id,
    )
    if data is None:
        return DataResponse(data=None)
    return DataResponse(data=ArchiveStatus.model_validate(data))


@router.post(
    "/websites/{slug}/archive", status_code=status.HTTP_202_ACCEPTED,
)
async def force_website_archive(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ArchiveStatus]:
    """Force a fresh Wayback snapshot of the website's public URL.

    All three rendering modes (STATIC / HYBRID / DYNAMIC) are
    accepted — Wayback only needs a URL that returns HTML, which the
    Aracne2 server emits in every mode.
    """
    website = await _resolve_website(db, slug)
    try:
        data = await archive_website(db, website, force=True)
    except ArchiveSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except IAError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Internet Archive submit failed: {exc}",
        )
    return DataResponse(
        data=ArchiveStatus.model_validate({
            "submitted_at": datetime.now(UTC),
            **data,
        })
    )


@router.post("/websites/{slug}/refresh")
async def refresh_website_archive(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ArchiveStatus]:
    """Re-poll a pending SPN2 job for a previously submitted website."""
    website = await _resolve_website(db, slug)
    try:
        data = await refresh_website_status(db, website)
    except ArchiveSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except IAError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Internet Archive status poll failed: {exc}",
        )
    return DataResponse(data=ArchiveStatus.model_validate(data))
