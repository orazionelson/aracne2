"""Dataverse Integration plugin — admin + per-collection / per-website router.

Endpoints (mounted under ``/api/v1``):

  GET  /plugins/dataverse/config                              [Admin]
  PUT  /plugins/dataverse/config                              [Admin]
  GET  /plugins/dataverse/collections/{slug}/status           [EiC+]
  POST /plugins/dataverse/collections/{slug}/deposit          [EiC+]
  GET  /plugins/dataverse/websites/{slug}/status              [EiC+]
  POST /plugins/dataverse/websites/{slug}/deposit             [EiC+]
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
from app.plugins.dataverse_integration.config import (
    K_AUTO_DEPOSIT,
    K_AUTO_PUBLISH,
    K_BASE_URL,
    K_CONTACT_EMAIL,
    K_CONTACT_NAME,
    K_DEFAULT_ALIAS,
    K_DEFAULT_SUBJECT,
    K_PUBLISH_TYPE,
    K_TOKEN,
    load_runtime_config,
)
from app.plugins.dataverse_integration.deposit import (
    DEPOSIT_KEY,
    PLUGIN_ID,
    WEBSITE_DEPOSIT_KEY,
    DepositSkipped,
    deposit_collection,
    deposit_website,
)
from app.plugins.dataverse_integration.schemas import (
    CollectionDepositRequest,
    DataverseConfig,
    DataverseConfigUpdate,
    DataverseDepositStatus,
    PublishType,
    WebsiteDepositRequest,
)
from app.plugins.dataverse_integration.service import DataverseError
from app.schemas.common import DataResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/plugins/dataverse", tags=["dataverse"])

_admin = Depends(require_role(min_role="Admin"))
_eic = Depends(require_role(min_role="EditorInChief"))


async def _write_setting(
    db: AsyncSession, key: str, value: str, actor: User,
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
            detail=f"Setting '{key}' missing — did migration 0064 run?",
        )
    row.value = stored
    row.updated_by = actor.id
    await db.flush()


def _config_response(cfg: Any) -> DataverseConfig:
    return DataverseConfig(
        token_set=bool(cfg.api_token),
        base_url=cfg.base_url,
        default_alias=cfg.default_alias,
        auto_deposit=cfg.auto_deposit,
        auto_publish=cfg.auto_publish,
        default_subject=cfg.default_subject,
        contact_name=cfg.contact_name,
        contact_email=cfg.contact_email,
        publish_type=cfg.publish_type if cfg.publish_type in (
            "major", "minor", "updatecurrent",
        ) else "major",
        public_base_url=cfg.public_base_url,
    )


@router.get("/config")
async def get_config(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DataverseConfig]:
    cfg = await load_runtime_config(db)
    return DataResponse(data=_config_response(cfg))


@router.put("/config")
async def update_config(
    body: DataverseConfigUpdate,
    actor: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DataverseConfig]:
    if body.api_token is not None:
        await _write_setting(db, K_TOKEN, body.api_token, actor)
    if body.base_url is not None:
        await _write_setting(db, K_BASE_URL, body.base_url, actor)
    if body.default_alias is not None:
        await _write_setting(db, K_DEFAULT_ALIAS, body.default_alias, actor)
    if body.auto_deposit is not None:
        await _write_setting(
            db, K_AUTO_DEPOSIT, "true" if body.auto_deposit else "false", actor,
        )
    if body.auto_publish is not None:
        await _write_setting(
            db, K_AUTO_PUBLISH, "true" if body.auto_publish else "false", actor,
        )
    if body.default_subject is not None:
        await _write_setting(db, K_DEFAULT_SUBJECT, body.default_subject, actor)
    if body.contact_name is not None:
        await _write_setting(db, K_CONTACT_NAME, body.contact_name, actor)
    if body.contact_email is not None:
        await _write_setting(db, K_CONTACT_EMAIL, body.contact_email, actor)
    if body.publish_type is not None:
        await _write_setting(db, K_PUBLISH_TYPE, body.publish_type, actor)
    await db.commit()
    cfg = await load_runtime_config(db)
    return DataResponse(data=_config_response(cfg))


# ── Collection deposit endpoints ──────────────────────────────────────────


async def _resolve_collection(db: AsyncSession, slug: str) -> Collection:
    col = await db.scalar(select(Collection).where(Collection.slug == slug))
    if col is None:
        raise HTTPException(
            status_code=404, detail=f"Collection '{slug}' not found",
        )
    return col


@router.get("/collections/{slug}/status")
async def get_collection_deposit_status(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DataverseDepositStatus | None]:
    from app.models.plugin import Plugin
    from app.services.plugin_data import PluginDataService

    col = await _resolve_collection(db, slug)
    plugin_row = await db.scalar(
        select(Plugin).where(Plugin.name == PLUGIN_ID),
    )
    if plugin_row is None:
        return DataResponse(data=None)
    svc = PluginDataService(plugin_id=plugin_row.id)
    data = await svc.get(
        db, entity_type="collection", key=DEPOSIT_KEY, entity_id=col.id,
    )
    if data is None:
        return DataResponse(data=None)
    return DataResponse(data=DataverseDepositStatus.model_validate(data))


@router.post(
    "/collections/{slug}/deposit", status_code=status.HTTP_202_ACCEPTED,
)
async def force_collection_deposit(
    slug: str,
    body: CollectionDepositRequest,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DataverseDepositStatus]:
    col = await _resolve_collection(db, slug)
    try:
        result = await deposit_collection(
            db, col, alias_override=body.alias, force=True,
        )
    except DepositSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DataverseError as exc:
        raise HTTPException(
            status_code=502, detail=f"Dataverse deposit failed: {exc}",
        )
    return DataResponse(
        data=DataverseDepositStatus(
            persistent_id=result.persistent_id,
            doi=result.doi or None,
            landing_url=result.landing_url,
            status="published" if result.status == "published" else "draft",
            submitted_at=datetime.now(UTC),
        )
    )


# ── Website deposit endpoints ─────────────────────────────────────────────


async def _resolve_website(db: AsyncSession, slug: str):  # type: ignore[no-untyped-def]
    from app.models.website import Website

    row = await db.scalar(select(Website).where(Website.slug == slug))
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Website '{slug}' not found",
        )
    return row


@router.get("/websites/{slug}/status")
async def get_website_deposit_status(
    slug: str,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DataverseDepositStatus | None]:
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
        db, entity_type="website", key=WEBSITE_DEPOSIT_KEY,
        entity_id=website.id,
    )
    if data is None:
        return DataResponse(data=None)
    return DataResponse(data=DataverseDepositStatus.model_validate(data))


@router.post(
    "/websites/{slug}/deposit", status_code=status.HTTP_202_ACCEPTED,
)
async def force_website_deposit(
    slug: str,
    body: WebsiteDepositRequest,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[DataverseDepositStatus]:
    website = await _resolve_website(db, slug)
    try:
        result = await deposit_website(
            db, website,
            upload_as_zip=body.upload_as_zip,
            alias_override=body.alias,
            force=True,
        )
    except DepositSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DataverseError as exc:
        raise HTTPException(
            status_code=502, detail=f"Dataverse deposit failed: {exc}",
        )
    return DataResponse(
        data=DataverseDepositStatus(
            persistent_id=result.persistent_id,
            doi=result.doi or None,
            landing_url=result.landing_url,
            status="published" if result.status == "published" else "draft",
            submitted_at=datetime.now(UTC),
        )
    )
