from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse

router = APIRouter(prefix="/viaf", tags=["viaf"])

_VIAF_AUTOSUGGEST = "https://www.viaf.org/viaf/AutoSuggest"
_TIMEOUT = 5.0


@router.get("/autosuggest")
async def viaf_autosuggest(
    query: Annotated[str, Query(min_length=2, max_length=100)],
    current_user: Annotated[User, Depends(require_role(min_role="User"))],
) -> DataResponse[list[str]]:
    """Proxy for VIAF AutoSuggest — returns a list of displayForm name strings."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.get(_VIAF_AUTOSUGGEST, params={"query": query})
            resp.raise_for_status()
            payload = resp.json()
            results: list[dict] = payload.get("result") or []
            names = [r["displayForm"] for r in results if r.get("displayForm")]
        except (httpx.HTTPError, KeyError, ValueError):
            names = []
    return DataResponse(data=names)
