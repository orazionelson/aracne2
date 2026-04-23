"""ROR plugin — public search proxy.

Single endpoint ``GET /plugins/ror/search`` that proxies the public
ROR v2 search API. Requires any authenticated user (the editor panel
runs for any editor, not just EiC+) and is rate-limited via the shared
slowapi instance to shield the upstream.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.ror.schemas import RorHit
from app.plugins.ror.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/ror", tags=["ror"])


@router.get("/search")
@limiter.limit("30/minute")
async def ror_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[RorHit]]:
    """Search the public ROR registry for *q* (institution name, acronym, …).

    Returns up to *rows* hits with display names, localised aliases,
    country, and institution types, ready for the editor to apply as a
    ``@ref="https://ror.org/..."`` on a TEI ``<orgName>`` element.
    Upstream hiccups degrade to ``data: []``.
    """
    hits = await search(q, rows=rows)
    return DataResponse(data=hits)
