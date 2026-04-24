"""CERL Thesaurus plugin — editor-side search proxy."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.cerl.schemas import CerlHit
from app.plugins.cerl.service import search
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/cerl", tags=["cerl"])


@router.get("/search")
@limiter.limit("30/minute")
async def cerl_search(
    request: Request,
    _: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    rows: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[CerlHit]]:
    """Search the CERL Thesaurus for *q*.

    Returns up to *rows* hits with display label, disambiguating
    detail (biographical dates, variant names, place), and an
    entity-kind bucket (``person`` / ``corporate`` / ``place`` /
    ``imprint`` / ``other``) used by the editor panel to validate
    against the enclosing TEI tag. Upstream hiccups degrade to
    ``data: []``.
    """
    hits = await search(q, rows=rows)
    return DataResponse(data=hits)
