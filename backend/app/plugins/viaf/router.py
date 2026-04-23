"""VIAF plugin — editor-side AutoSuggest proxy.

Single endpoint ``GET /plugins/viaf/search`` that proxies the public
VIAF AutoSuggest API. Requires any authenticated user (the editor
panel runs for any editor, not just EiC+) and is rate-limited via
the shared slowapi instance to shield the upstream.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.viaf.schemas import ViafHit
from app.plugins.viaf.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/viaf", tags=["viaf"])


@router.get("/search")
@limiter.limit("30/minute")
async def viaf_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[ViafHit]]:
    """Search VIAF AutoSuggest for *q* (person name, institution name).

    Returns up to *rows* hits with display label, name type
    (``personal`` / ``corporate``), and the VIAF URI. Applied as
    ``@ref="http://viaf.org/viaf/..."`` on a TEI ``<persName>`` or
    ``<orgName>`` element. Upstream hiccups degrade to ``data: []``.
    """
    hits = await search(q, rows=rows)
    return DataResponse(data=hits)
