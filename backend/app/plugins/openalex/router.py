"""OpenAlex plugin — editor-side search proxy + contact-email config.

Two endpoints:

- ``GET /plugins/openalex/search`` — User+, 30/min per IP.
- ``GET /PUT /plugins/openalex/config`` — Admin-only. One tunable: the
  polite-pool contact email, same pattern as the CrossRef plugin.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins.openalex.schemas import (
    OpenAlexConfig,
    OpenAlexConfigUpdate,
    OpenAlexHit,
)
from app.plugins.openalex.service import search
from app.schemas.common import DataResponse
from app.services.settings import get_decrypted_setting

router = APIRouter(prefix="/plugins/openalex", tags=["openalex"])

K_CONTACT_EMAIL = "openalex_contact_email"


async def _contact_email(db: AsyncSession) -> str:
    return (await get_decrypted_setting(db, K_CONTACT_EMAIL) or "").strip()


# ── Search ──────────────────────────────────────────────────────────────────


@router.get("/search")
@limiter.limit("30/minute")
async def openalex_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[OpenAlexHit]]:
    """Search OpenAlex works for *q*. Returns up to *rows* hits, each
    with a lightweight preview plus a ready-to-insert ``<biblStruct>``
    XML fragment. Upstream hiccups degrade to ``data: []``.
    """
    email = await _contact_email(db) or app_settings.admin_email
    hits = await search(q, rows=rows, contact_email=email)
    return DataResponse(data=hits)


# ── Config ──────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config(
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[OpenAlexConfig]:
    return DataResponse(
        data=OpenAlexConfig(
            contact_email=await _contact_email(db),
            fallback_email=app_settings.admin_email,
        )
    )


@router.put("/config")
async def update_config(
    body: OpenAlexConfigUpdate,
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[OpenAlexConfig]:
    if body.contact_email is not None:
        row = await db.get(SystemSetting, K_CONTACT_EMAIL)
        value = body.contact_email.strip()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Setting '{K_CONTACT_EMAIL}' missing — did migration 0058 run?",
            )
        row.value = value
        await db.flush()
    await db.commit()
    return DataResponse(
        data=OpenAlexConfig(
            contact_email=await _contact_email(db),
            fallback_email=app_settings.admin_email,
        )
    )
