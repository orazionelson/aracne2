"""Zenodo deposit — admin router.

Endpoints (all under ``/api/v1`` mount):

- ``GET  /plugins/zenodo-deposit/config``    → current non-sensitive config
- ``PUT  /plugins/zenodo-deposit/config``    → partial update (Admin only)
- ``GET  /plugins/zenodo-deposit/collections/{slug}/status``
                                             → last deposit record, or 404
- ``POST /plugins/zenodo-deposit/collections/{slug}/deposit``
                                             → force a fresh deposit attempt
"""

from __future__ import annotations

from typing import Annotated, cast

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
from app.plugins.zenodo_deposit.config import (
    K_ACCESS_RIGHT,
    K_AUTO_PUBLISH,
    K_BASE_URL,
    K_COMMUNITY,
    K_PUBLICATION_TYPE,
    K_PUBLIC_BASE_URL,
    K_TOKEN,
    load_runtime_config,
)
from app.plugins.zenodo_deposit.deposit import (
    DEPOSIT_KEY,
    PLUGIN_ID,
    DepositSkipped,
    deposit_collection,
)
from app.plugins.zenodo_deposit.schemas import (
    AccessRight,
    DepositStatus,
    PublicationType,
    ZenodoConfigResponse,
    ZenodoConfigUpdate,
)
from app.plugins.zenodo_deposit.service import ZenodoError
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/zenodo-deposit", tags=["zenodo-deposit"])

_admin = Depends(require_role(min_role="Admin"))
_eic = Depends(require_role(min_role="EditorInChief"))


async def _write_setting(
    db: AsyncSession, key: str, value: str, actor: User
) -> None:
    """Upsert a single setting row, encrypting if the key is sensitive."""
    stored = encrypt_value(value, app_settings.jwt_secret) if key in SENSITIVE_KEYS else value
    row = await db.get(SystemSetting, key)
    if row is None:
        raise HTTPException(
            status_code=500,
            detail=f"Setting '{key}' missing — did migration 0047 run?",
        )
    row.value = stored
    row.updated_by = actor.id
    await db.flush()


@router.get("/config")
async def get_config(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ZenodoConfigResponse]:
    cfg = await load_runtime_config(db)
    return DataResponse(
        data=ZenodoConfigResponse(
            token_set=bool(cfg.api_token),
            base_url=cfg.base_url,
            default_community=cfg.default_community,
            auto_publish=cfg.auto_publish,
            access_right=cast(AccessRight, cfg.access_right),
            publication_type=cast(PublicationType, cfg.publication_type),
            public_base_url=cfg.public_base_url,
        )
    )


@router.put("/config")
async def update_config(
    body: ZenodoConfigUpdate,
    actor: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ZenodoConfigResponse]:
    if body.api_token is not None:
        await _write_setting(db, K_TOKEN, body.api_token, actor)
    if body.base_url is not None:
        await _write_setting(db, K_BASE_URL, body.base_url, actor)
    if body.default_community is not None:
        await _write_setting(db, K_COMMUNITY, body.default_community, actor)
    if body.auto_publish is not None:
        await _write_setting(
            db, K_AUTO_PUBLISH, "true" if body.auto_publish else "false", actor
        )
    if body.access_right is not None:
        await _write_setting(db, K_ACCESS_RIGHT, body.access_right, actor)
    if body.publication_type is not None:
        await _write_setting(db, K_PUBLICATION_TYPE, body.publication_type, actor)
    if body.public_base_url is not None:
        await _write_setting(db, K_PUBLIC_BASE_URL, body.public_base_url, actor)

    await db.commit()

    cfg = await load_runtime_config(db)
    return DataResponse(
        data=ZenodoConfigResponse(
            token_set=bool(cfg.api_token),
            base_url=cfg.base_url,
            default_community=cfg.default_community,
            auto_publish=cfg.auto_publish,
            access_right=cast(AccessRight, cfg.access_right),
            publication_type=cast(PublicationType, cfg.publication_type),
            public_base_url=cfg.public_base_url,
        )
    )


async def _resolve_collection(db: AsyncSession, slug: str) -> Collection:
    col = await db.scalar(select(Collection).where(Collection.slug == slug))
    if col is None:
        raise HTTPException(status_code=404, detail=f"Collection '{slug}' not found")
    return col


@router.get("/collections/{slug}/status")
async def get_deposit_status(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DepositStatus | None]:
    """Return the most recent deposit record for a collection, or 404 if none."""
    from app.models.plugin import Plugin
    from app.services.plugin_data import PluginDataService

    col = await _resolve_collection(db, slug)
    plugin_row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if plugin_row is None:
        return DataResponse(data=None)
    svc = PluginDataService(plugin_id=plugin_row.id)
    data = await svc.get(
        db, entity_type="collection", key=DEPOSIT_KEY, entity_id=col.id
    )
    if data is None:
        return DataResponse(data=None)
    return DataResponse(data=DepositStatus.model_validate(data))


@router.post("/collections/{slug}/deposit", status_code=status.HTTP_202_ACCEPTED)
async def force_deposit(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DepositStatus]:
    """Force a deposit attempt for a collection even if it has already been deposited."""
    col = await _resolve_collection(db, slug)
    try:
        result = await deposit_collection(db, col, force=True)
    except DepositSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ZenodoError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Zenodo deposit failed: {exc}",
        )
    from datetime import UTC, datetime

    return DataResponse(
        data=DepositStatus(
            deposit_id=result.id,
            doi=result.doi,
            record_url=result.record_url or None,
            status="published" if result.status == "published" else "draft",
            submitted_at=datetime.now(UTC),
        )
    )
