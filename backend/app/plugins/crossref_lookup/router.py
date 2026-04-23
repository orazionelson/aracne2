"""CrossRef Lookup — non-native plugin router.

Endpoints (all under ``/api/v1`` mount):

- ``GET  /plugins/crossref-lookup/config``      → current non-sensitive config
- ``PUT  /plugins/crossref-lookup/config``      → Admin-only update
- ``GET  /plugins/crossref-lookup/lookup``      → resolve a DOI to biblStruct
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.exceptions import ExternalServiceError, NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins.crossref_lookup.schemas import (
    BiblStructPreview,
    CrossrefLookupConfigResponse,
    CrossrefLookupConfigUpdate,
    CrossrefLookupResponse,
)
from app.plugins.crossref_lookup.service import resolve_doi
from app.schemas.common import DataResponse
from app.services.settings import get_decrypted_setting

router = APIRouter(prefix="/plugins/crossref-lookup", tags=["crossref-lookup"])

logger = structlog.get_logger()

_admin = Depends(require_role(min_role="Admin"))
_eic = Depends(require_role(min_role="EditorInChief"))

K_CONTACT_EMAIL = "crossref_contact_email"


async def _load_contact_email(db: AsyncSession) -> str:
    """Return the configured contact email, or an empty string.

    Falls back to ``admin_email`` at router call time (not here) so the
    config response faithfully shows what the operator configured.
    """
    return (await get_decrypted_setting(db, K_CONTACT_EMAIL) or "").strip()


@router.get("/config")
async def get_config(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CrossrefLookupConfigResponse]:
    contact = await _load_contact_email(db)
    return DataResponse(
        data=CrossrefLookupConfigResponse(
            contact_email=contact,
            fallback_email=app_settings.admin_email,
        )
    )


@router.put("/config")
async def update_config(
    body: CrossrefLookupConfigUpdate,
    actor: Annotated[User, Depends(require_role(min_role="Admin"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CrossrefLookupConfigResponse]:
    if body.contact_email is not None:
        row = await db.get(SystemSetting, K_CONTACT_EMAIL)
        if row is None:
            raise HTTPException(
                status_code=500,
                detail=f"Setting '{K_CONTACT_EMAIL}' missing — did migration 0055 run?",
            )
        row.value = body.contact_email.strip()
        row.updated_by = actor.id
        await db.flush()
    await db.commit()
    contact = await _load_contact_email(db)
    return DataResponse(
        data=CrossrefLookupConfigResponse(
            contact_email=contact,
            fallback_email=app_settings.admin_email,
        )
    )


@router.get("/lookup")
@limiter.limit("30/minute")
async def crossref_lookup(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    doi: Annotated[str, Query(min_length=3, max_length=256)],
) -> DataResponse[CrossrefLookupResponse]:
    """Resolve *doi* via CrossRef and return a TEI biblStruct fragment.

    ACL: EditorInChief+ — the endpoint issues outbound traffic and the
    result is intended for editorial use only.

    Errors are mapped to the platform's convention:

    - 404 when CrossRef does not know the DOI;
    - 502 on any other upstream failure (timeout, 5xx, parse error).
    """
    contact = await _load_contact_email(db) or app_settings.admin_email
    try:
        result = await resolve_doi(doi, contact_email=contact)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ExternalServiceError as exc:
        logger.warning("crossref_lookup_failed", doi=doi, error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))

    return DataResponse(
        data=CrossrefLookupResponse(
            xml_id=result.xml_id,
            biblstruct_xml=result.biblstruct_xml,
            preview=BiblStructPreview(
                title=result.preview.title,
                authors=result.preview.authors,
                year=result.preview.year,
                container=result.preview.container,
                publisher=result.preview.publisher,
                doi=result.preview.doi,
                type=result.preview.type,
            ),
        )
    )
