"""Trismegistos plugin — ID resolver endpoint.

The single public endpoint is ``POST /plugins/trismegistos/resolve``
which takes ``{kind, identifier, source}`` and returns either a
``TrismegistosHit`` or ``null`` when the ID does not resolve. The
plugin has no secret settings and therefore no ``/config`` endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.plugins.trismegistos.schemas import (
    TrismegistosHit,
    TrismegistosResolveRequest,
)
from app.plugins.trismegistos.service import resolve
from app.schemas.common import DataResponse

router = APIRouter(prefix="/plugins/trismegistos", tags=["trismegistos"])


@router.post("/resolve")
@limiter.limit("30/minute")
async def trismegistos_resolve(
    request: Request,
    body: TrismegistosResolveRequest,
    _: Annotated[User, Depends(require_role(min_role="User"))],
) -> DataResponse[TrismegistosHit | None]:
    """Resolve a Trismegistos ID and return the hit, or ``null``.

    - ``kind="person"`` composes the canonical TM URL without a
      network call (TM has no person JSON endpoint).
    - ``kind="place"`` calls ``georelations/<id>``.
    - ``kind="text"`` calls ``texrelations/<id>?source=<src>`` —
      ``source`` defaults to ``trismegistos`` (direct TM ID lookup);
      any other value triggers a partner-DB reverse lookup.
    """
    hit = await resolve(
        kind=body.kind,
        identifier=body.identifier,
        source=body.source,
    )
    return DataResponse(data=hit)
