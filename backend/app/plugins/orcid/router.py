"""ORCID plugin — public search proxy.

Single endpoint ``GET /plugins/orcid/search`` that proxies the public
ORCID ``expanded-search`` API. Requires any authenticated user (the
editor panel runs for any editor, not just EiC+) and is rate-limited
via the shared slowapi instance to shield the upstream.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.orcid.schemas import OrcidHit
from app.plugins.orcid.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/orcid", tags=["orcid"])


@router.get("/search")
@limiter.limit("30/minute")
async def orcid_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[OrcidHit]]:
    """Search the public ORCID registry for *q* (name, keyword, …).

    Returns up to *rows* hits with display names and — when available —
    institutional affiliations, ready for the editor to apply as a
    ``@ref="https://orcid.org/..."`` on a TEI ``<persName>`` element.
    Upstream hiccups degrade to ``data: []``.
    """
    hits = await search(q, rows=rows)
    return DataResponse(data=hits)
