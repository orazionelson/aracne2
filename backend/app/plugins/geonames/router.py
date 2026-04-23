"""GeoNames plugin — editor-side place-search proxy + URL-format config.

Two endpoints:

- ``GET /plugins/geonames/search`` — User+, 30/min per IP, returns
  GeoNames populated-place hits ready to be written as ``@ref`` on a
  TEI ``<placeName>``. The URI format (web vs semantic-web) respects
  the plugin's ``url_format`` setting.

- ``GET / PUT /plugins/geonames/config`` — Admin-only. Single tunable:
  ``url_format`` in ``{"web", "sws"}``. The username is shown
  read-only because it lives in the shared ``system_settings`` row
  (key ``geonames_username``) also used by the core router and
  the collection-create form.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins.geonames.schemas import (
    GeonamesConfig,
    GeonamesConfigUpdate,
    GeonamesHit,
    UriFormat,
)
from app.plugins.geonames.service import search
from app.schemas.common import DataResponse
from app.services.geonames_auth import get_geonames_username

router = APIRouter(prefix="/plugins/geonames", tags=["geonames"])

K_URL_FORMAT = "geonames_plugin_url_format"
_DEFAULT_URL_FORMAT: UriFormat = "web"


async def _get_url_format(db: AsyncSession) -> UriFormat:
    row = await db.get(SystemSetting, K_URL_FORMAT)
    if row is None:
        return _DEFAULT_URL_FORMAT
    value = (row.value or "").strip()
    if value in ("web", "sws"):
        return value  # type: ignore[return-value]
    return _DEFAULT_URL_FORMAT


# ── Search ──────────────────────────────────────────────────────────────────


@router.get("/search")
@limiter.limit("30/minute")
async def geonames_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[GeonamesHit]]:
    """Search GeoNames populated places for *q*.

    Returns up to *rows* hits with display label, region, country, and
    the URI format configured for this plugin. Upstream hiccups and
    quota exhaustion degrade to ``data: []``.
    """
    username = await get_geonames_username(db)
    fmt = await _get_url_format(db)
    hits = await search(q, username=username, url_format=fmt, rows=rows)
    return DataResponse(data=hits)


# ── Config ──────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config(
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GeonamesConfig]:
    """Read the URL format + a snapshot of the shared username."""
    return DataResponse(
        data=GeonamesConfig(
            url_format=await _get_url_format(db),
            geonames_username=await get_geonames_username(db),
        )
    )


@router.put("/config")
async def update_config(
    body: GeonamesConfigUpdate,
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GeonamesConfig]:
    """Update the plugin-local URL format. The username lives in the
    shared ``system_settings`` row and is edited from ``/admin/settings``
    — this endpoint does not touch it."""
    if body.url_format is not None:
        row = await db.get(SystemSetting, K_URL_FORMAT)
        if row is None:
            row = SystemSetting(
                key=K_URL_FORMAT, value=body.url_format, type="string",
            )
            db.add(row)
        else:
            row.value = body.url_format
        await db.flush()

    await db.commit()
    return DataResponse(
        data=GeonamesConfig(
            url_format=await _get_url_format(db),
            geonames_username=await get_geonames_username(db),
        )
    )
