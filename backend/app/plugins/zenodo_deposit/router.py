"""Zenodo deposit — admin router.

Endpoints (all under ``/api/v1`` mount):

- ``GET  /plugins/zenodo-deposit/config``                 → current non-sensitive config
- ``PUT  /plugins/zenodo-deposit/config``                 → partial update (Admin only)
- ``GET  /plugins/zenodo-deposit/resource-types``         → proxied InvenioRDM vocabulary
- ``GET  /plugins/zenodo-deposit/collections/{slug}/status`` → last deposit record
- ``POST /plugins/zenodo-deposit/collections/{slug}/deposit`` → force a fresh deposit
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

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
from app.plugins.zenodo_deposit.config import (
    K_ACCESS,
    K_AUTO_PUBLISH,
    K_BASE_URL,
    K_COMMUNITY,
    K_PUBLIC_BASE_URL,
    K_RESOURCE_TYPE,
    K_TOKEN,
    load_runtime_config,
)
from app.plugins.zenodo_deposit.deposit import (
    DEPOSIT_KEY,
    PLUGIN_ID,
    WEBSITE_DEPOSIT_KEY,
    DepositSkipped,
    deposit_collection,
    deposit_website,
)
from app.plugins.zenodo_deposit.schemas import (
    AccessMode,
    DepositStatus,
    ResourceTypeOption,
    WebsiteDepositRequest,
    WebsiteDepositStatus,
    ZenodoConfigResponse,
    ZenodoConfigUpdate,
)
from app.plugins.zenodo_deposit.service import ZenodoClient, ZenodoError
from app.schemas.common import DataResponse

logger = structlog.get_logger()

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
            detail=f"Setting '{key}' missing — did migration 0048 run?",
        )
    row.value = stored
    row.updated_by = actor.id
    await db.flush()


def _config_response(cfg: Any) -> ZenodoConfigResponse:
    return ZenodoConfigResponse(
        token_set=bool(cfg.api_token),
        base_url=cfg.base_url,
        default_community=cfg.default_community,
        auto_publish=cfg.auto_publish,
        access=cast(AccessMode, cfg.access),
        resource_type=cfg.resource_type,
        public_base_url=cfg.public_base_url,
    )


@router.get("/config")
async def get_config(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[ZenodoConfigResponse]:
    cfg = await load_runtime_config(db)
    return DataResponse(data=_config_response(cfg))


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
    if body.access is not None:
        await _write_setting(db, K_ACCESS, body.access, actor)
    if body.resource_type is not None:
        await _write_setting(db, K_RESOURCE_TYPE, body.resource_type, actor)
    if body.public_base_url is not None:
        await _write_setting(db, K_PUBLIC_BASE_URL, body.public_base_url, actor)

    await db.commit()

    cfg = await load_runtime_config(db)
    return DataResponse(data=_config_response(cfg))


# ── Resource-type vocabulary proxy ───────────────────────────────────────────
#
# Fetch the live vocabulary from Zenodo and normalise it into a flat list the
# admin UI can render as a grouped dropdown. Falls back to a hard-coded
# minimal list on any error so the UI never shows an empty dropdown (the
# user can still pick a sensible default and re-save once Zenodo is
# reachable).

# Group label derived from the id prefix when Zenodo does not expose a
# hierarchy. Keeps the dropdown navigable — one optgroup per "family".
_ID_PREFIX_GROUPS: dict[str, str] = {
    "publication": "Publication",
    "image": "Image",
    "dataset": "Dataset",
    "software": "Software",
    "video": "Video / Audio",
    "audio": "Video / Audio",
    "lesson": "Lesson",
    "poster": "Poster",
    "presentation": "Presentation",
    "physicalobject": "Physical object",
    "model": "Model",
    "workflow": "Workflow",
    "other": "Other",
}


def _group_for_id(vocab_id: str) -> str:
    prefix = vocab_id.split("-", 1)[0]
    return _ID_PREFIX_GROUPS.get(prefix, "Other")


def _label_from_title(title: Any, fallback: str) -> str:
    if isinstance(title, dict):
        for lang in ("en", "it"):
            val = title.get(lang)
            if isinstance(val, str) and val:
                return val
        for val in title.values():
            if isinstance(val, str) and val:
                return val
    if isinstance(title, str) and title:
        return title
    return fallback


# Fallback list used when Zenodo is unreachable at first paint. Small but
# covers the vast majority of scholarly-edition use cases.
_FALLBACK_RESOURCE_TYPES: list[ResourceTypeOption] = [
    ResourceTypeOption(id="publication-other", label="Publication / Other", group="Publication"),
    ResourceTypeOption(id="publication-book", label="Publication / Book", group="Publication"),
    ResourceTypeOption(id="publication-section", label="Publication / Book section", group="Publication"),
    ResourceTypeOption(id="publication-article", label="Publication / Journal article", group="Publication"),
    ResourceTypeOption(id="publication-preprint", label="Publication / Preprint", group="Publication"),
    ResourceTypeOption(id="publication-thesis", label="Publication / Thesis", group="Publication"),
    ResourceTypeOption(id="publication-report", label="Publication / Report", group="Publication"),
    ResourceTypeOption(id="publication-annotationcollection", label="Publication / Annotation collection", group="Publication"),
    ResourceTypeOption(id="dataset", label="Dataset", group="Dataset"),
    ResourceTypeOption(id="image-photo", label="Image / Photo", group="Image"),
    ResourceTypeOption(id="image-figure", label="Image / Figure", group="Image"),
    ResourceTypeOption(id="image-other", label="Image / Other", group="Image"),
    ResourceTypeOption(id="poster", label="Poster", group="Poster"),
    ResourceTypeOption(id="presentation", label="Presentation", group="Presentation"),
    ResourceTypeOption(id="lesson", label="Lesson", group="Lesson"),
    ResourceTypeOption(id="other", label="Other", group="Other"),
]


@router.get("/resource-types")
async def list_resource_types(
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[ResourceTypeOption]]:
    """Proxy Zenodo's resource-type vocabulary for the admin dropdown.

    Falls back to the hard-coded list in this module if Zenodo is
    unreachable so the admin UI always has something to render.
    """
    cfg = await load_runtime_config(db)
    if not cfg.api_token:
        # Token not configured yet — cannot call Zenodo; return fallback.
        return DataResponse(data=_FALLBACK_RESOURCE_TYPES)

    client = ZenodoClient(base_url=cfg.base_url, api_token=cfg.api_token)
    try:
        hits = await client.fetch_resource_types()
    except ZenodoError as exc:
        logger.warning("zenodo_vocabulary_fetch_failed", error=str(exc))
        return DataResponse(data=_FALLBACK_RESOURCE_TYPES)

    options: list[ResourceTypeOption] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        vocab_id = hit.get("id")
        if not isinstance(vocab_id, str) or not vocab_id:
            continue
        label = _label_from_title(hit.get("title"), vocab_id)
        options.append(
            ResourceTypeOption(
                id=vocab_id,
                label=label,
                group=_group_for_id(vocab_id),
            )
        )

    if not options:
        return DataResponse(data=_FALLBACK_RESOURCE_TYPES)

    options.sort(key=lambda o: (o.group, o.label))
    return DataResponse(data=options)


# ── Per-collection deposit endpoints ─────────────────────────────────────────


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
    """Return the most recent deposit record for a collection, or ``null``."""
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

    return DataResponse(
        data=DepositStatus(
            deposit_id=result.id,
            doi=result.doi,
            record_url=result.record_url or None,
            status="published" if result.status == "published" else "draft",
            submitted_at=datetime.now(UTC),
        )
    )


# ── Per-website deposit endpoints ────────────────────────────────────────────


async def _resolve_website(db: AsyncSession, slug: str):  # type: ignore[no-untyped-def]
    """Local resolver — kept inline to avoid pulling the websites router
    package just for one helper. Returns 404 on miss."""
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
) -> DataResponse[WebsiteDepositStatus | None]:
    """Most recent website-deposit record for *slug*, or ``null``."""
    from app.models.plugin import Plugin
    from app.services.plugin_data import PluginDataService

    website = await _resolve_website(db, slug)
    plugin_row = await db.scalar(select(Plugin).where(Plugin.name == PLUGIN_ID))
    if plugin_row is None:
        return DataResponse(data=None)
    svc = PluginDataService(plugin_id=plugin_row.id)
    data = await svc.get(
        db, entity_type="website", key=WEBSITE_DEPOSIT_KEY, entity_id=website.id,
    )
    if data is None:
        return DataResponse(data=None)
    return DataResponse(data=WebsiteDepositStatus.model_validate(data))


@router.post(
    "/websites/{slug}/deposit", status_code=status.HTTP_202_ACCEPTED,
)
async def force_website_deposit(
    slug: str,
    body: WebsiteDepositRequest,
    _: Annotated[None, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[WebsiteDepositStatus]:
    """Force a (re-)deposit of the website's rendered output. Refuses
    when the website is DYNAMIC or has not been built (409). Returns
    502 when Zenodo itself rejects the request."""
    website = await _resolve_website(db, slug)
    try:
        result = await deposit_website(
            db, website,
            upload_as_zip=body.upload_as_zip,
            force=True,
        )
    except DepositSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ZenodoError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Zenodo deposit failed: {exc}",
        )

    return DataResponse(
        data=WebsiteDepositStatus(
            deposit_id=result.id,
            doi=result.doi,
            record_url=result.record_url or None,
            status="published" if result.status == "published" else "draft",
            submitted_at=datetime.now(UTC),
            uploaded_as_zip=body.upload_as_zip,
        )
    )
