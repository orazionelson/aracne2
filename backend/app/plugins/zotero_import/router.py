"""Zotero import plugin — admin config + per-collection preview/import."""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import SENSITIVE_KEYS, encrypt_value
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.collection import Collection
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins.zotero_import.config import (
    K_API_BASE,
    K_API_KEY,
    K_LIBRARY_ID,
    K_LIBRARY_TYPE,
    load_runtime_config,
)
from app.plugins.zotero_import.importer import (
    ImportSkipped,
    commit_import,
    preview,
)
from app.plugins.zotero_import.schemas import (
    ImportPreview,
    ImportRequest,
    ImportResult,
    LibraryType,
    ZoteroConfigResponse,
    ZoteroConfigUpdate,
)
from app.plugins.zotero_import.service import ZoteroError
from app.schemas.common import DataResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/plugins/zotero-import", tags=["zotero-import"])

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
            detail=f"Setting '{key}' missing — did migration 0053 run?",
        )
    row.value = stored
    row.updated_by = actor.id
    await db.flush()


def _to_config_response(cfg: Any) -> ZoteroConfigResponse:
    return ZoteroConfigResponse(
        api_key_set=bool(cfg.api_key),
        library_type=cfg.library_type,  # already normalised by load_runtime_config
        library_id=cfg.library_id,
        api_base=cfg.api_base,
    )


@router.get("/config")
async def get_config(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ZoteroConfigResponse]:
    cfg = await load_runtime_config(db)
    return DataResponse(data=_to_config_response(cfg))


@router.put("/config")
async def update_config(
    body: ZoteroConfigUpdate,
    actor: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ZoteroConfigResponse]:
    if body.api_key is not None:
        await _write_setting(db, K_API_KEY, body.api_key, actor)
    if body.library_type is not None:
        await _write_setting(db, K_LIBRARY_TYPE, body.library_type, actor)
    if body.library_id is not None:
        await _write_setting(db, K_LIBRARY_ID, body.library_id.strip(), actor)
    if body.api_base is not None:
        await _write_setting(db, K_API_BASE, body.api_base.strip().rstrip("/"), actor)
    await db.commit()
    cfg = await load_runtime_config(db)
    return DataResponse(data=_to_config_response(cfg))


async def _resolve_collection(db: AsyncSession, slug: str) -> Collection:
    col = await db.scalar(select(Collection).where(Collection.slug == slug))
    if col is None:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    return col


@router.post("/collections/{slug}/preview")
async def preview_import(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ImportPreview]:
    """Fetch the configured Zotero library and diff it against what has
    already been imported for this collection. Does not write anything."""
    col = await _resolve_collection(db, slug)
    try:
        result = await preview(db, col)
    except ImportSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ZoteroError as exc:
        raise HTTPException(
            status_code=502, detail=f"Zotero request failed: {exc}"
        )
    return DataResponse(data=result)


@router.post("/collections/{slug}/import")
async def do_import(
    slug: str,
    body: ImportRequest,
    actor: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ImportResult]:
    """Persist the requested Zotero items as a new bibliography version."""
    col = await _resolve_collection(db, slug)
    try:
        result = await commit_import(
            db, col, actor.id, keys=body.keys, all_new=body.all_new
        )
    except ImportSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ZoteroError as exc:
        raise HTTPException(
            status_code=502, detail=f"Zotero request failed: {exc}"
        )
    return DataResponse(data=result)


# Re-export for the router registration expression below.
_ = LibraryType
