"""Wikidata plugin — editor-side search proxy.

Single endpoint ``GET /plugins/wikidata/search``. Requires any
authenticated user (the editor panel runs for every editor, not only
EiC+) and is rate-limited via the shared slowapi instance to shield
the upstream from noisy search bursts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.wikidata.schemas import WikidataHit
from app.plugins.wikidata.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/wikidata", tags=["wikidata"])


@router.get("/search")
@limiter.limit("30/minute")
async def wikidata_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    lang: Annotated[
        str,
        Query(
            min_length=2,
            max_length=8,
            pattern=r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$",
        ),
    ] = "it",
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[WikidataHit]]:
    """Search Wikidata entities matching *q* in the given *lang*.

    Returns up to *limit* hits, each with its canonical URI ready to
    be used as a TEI ``@ref`` value. When the upstream call fails the
    response degrades to ``data: []`` — the editor UI treats that as
    "no results" so no disruptive error surfaces.
    """
    hits = await search(q, lang=lang, limit=limit)
    return DataResponse(data=hits)
