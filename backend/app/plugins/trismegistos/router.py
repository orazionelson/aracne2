"""Trismegistos plugin — search + API-key config."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import encrypt_value
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins.trismegistos.schemas import (
    TrismegistosConfig,
    TrismegistosConfigUpdate,
    TrismegistosHit,
)
from app.plugins.trismegistos.service import search
from app.schemas.common import DataResponse
from app.services.settings import get_decrypted_setting

router = APIRouter(prefix="/plugins/trismegistos", tags=["trismegistos"])

K_API_KEY = "trismegistos_api_key"


async def _api_key(db: AsyncSession) -> str:
    return (await get_decrypted_setting(db, K_API_KEY) or "").strip()


# ── Search ──────────────────────────────────────────────────────────────────


@router.get("/search")
@limiter.limit("30/minute")
async def trismegistos_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[TrismegistosHit]]:
    """Search Trismegistos for *q* across persons, places, and texts.

    Returns ``503 TMG_API_KEY_MISSING`` when the admin has not
    configured an API key (the frontend renders a banner prompting
    registration).
    """
    key = await _api_key(db)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "TMG_API_KEY_MISSING",
                "message": (
                    "Trismegistos API key not configured. "
                    "Register at https://www.trismegistos.org/api "
                    "and set the key in the plugin config."
                ),
            },
        )
    hits = await search(q, api_key=key, rows=rows)
    return DataResponse(data=hits)


# ── Config ──────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config(
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TrismegistosConfig]:
    key = await _api_key(db)
    return DataResponse(
        data=TrismegistosConfig(
            api_key_set=bool(key),
        )
    )


@router.put("/config")
async def update_config(
    body: TrismegistosConfigUpdate,
    _: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[TrismegistosConfig]:
    if body.api_key is not None:
        row = await db.get(SystemSetting, K_API_KEY)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Setting '{K_API_KEY}' missing — did migration 0058 run?",
            )
        value = body.api_key.strip()
        # Empty → clear the stored ciphertext. Non-empty → Fernet-encrypt
        # with the same derivation used by the rest of SENSITIVE_KEYS.
        row.value = encrypt_value(value, app_settings.jwt_secret) if value else ""
        await db.flush()
    await db.commit()
    return DataResponse(
        data=TrismegistosConfig(
            api_key_set=bool(await _api_key(db)),
        )
    )
