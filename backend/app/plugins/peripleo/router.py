"""Peripleo plugin — editor-side search proxy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.peripleo.schemas import PeripleoHit
from app.plugins.peripleo.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/peripleo", tags=["peripleo"])


@router.get("/search")
@limiter.limit("30/minute")
async def peripleo_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[PeripleoHit]]:
    """Search Peripleo (Pelagios aggregator) for *q*.

    Returns up to *rows* ancient-world place hits, each carrying the
    canonical URI of the source gazetteer (Pleiades, iDAI, etc.).
    Apply as ``@ref`` on a TEI ``<placeName>``. Upstream hiccups
    degrade to ``data: []``.
    """
    hits = await search(q, rows=rows)
    return DataResponse(data=hits)
