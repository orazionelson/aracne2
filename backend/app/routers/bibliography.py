"""Bibliography — external-service integrations that produce TEI biblStruct.

Currently hosts only the CrossRef DOI resolver. Future entries (ISBN via
Open Library, identifier normalisation, etc.) belong here alongside it so
the frontend has a stable prefix for all "resolve an external reference"
calls.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import settings
from app.core.exceptions import ExternalServiceError, NotFoundError
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.bibliography import BiblStructPreview, CrossrefLookupResponse
from app.schemas.common import DataResponse
from app.services.crossref import resolve_doi

router = APIRouter(prefix="/bibliography", tags=["bibliography"])

logger = structlog.get_logger()


@router.get("/crossref")
@limiter.limit("30/minute")
async def crossref_lookup(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="EditorInChief"))],
    doi: Annotated[str, Query(min_length=3, max_length=256)],
) -> DataResponse[CrossrefLookupResponse]:
    """Resolve *doi* via CrossRef and return a TEI biblStruct fragment.

    ACL: EditorInChief+ — the endpoint issues outbound traffic and the
    result is intended for editorial use only.

    Errors are mapped to the platform's convention:

    - 404 when CrossRef does not know the DOI (returns an honest
      "resource not found", not a transport error);
    - 502 on any other upstream failure (timeout, 5xx, parse error) — we
      never surface raw CrossRef error bodies to the client.
    """
    contact = (settings.crossref_contact_email or settings.admin_email or "").strip()
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
