"""Getty AAT plugin — editor-side SPARQL search proxy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.getty_aat.schemas import GettyAatHit
from app.plugins.getty_aat.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/getty-aat", tags=["getty_aat"])


@router.get("/search")
@limiter.limit("30/minute")
async def getty_aat_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[GettyAatHit]]:
    """Search the Getty AAT via SPARQL for concepts matching *q*.

    Returns up to *rows* hits with English label, scope note (short
    definition), and the canonical ``http://vocab.getty.edu/aat/{id}``
    URI ready to apply as ``@ref`` on a TEI ``<term>`` element.
    Upstream hiccups degrade to ``data: []``.
    """
    hits = await search(q, rows=rows)
    return DataResponse(data=hits)
