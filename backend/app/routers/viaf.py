from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, Query

from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse

router = APIRouter(prefix="/viaf", tags=["viaf"])

_VIAF_AUTOSUGGEST = "https://viaf.org/viaf/AutoSuggest"
_TIMEOUT = 8.0
_HEADERS = {"User-Agent": "Aracne2/1.0 (TEI CMS; https://github.com/orazionelson/aracne2)"}

logger = structlog.get_logger()


@router.get("/autosuggest")
async def viaf_autosuggest(
    query: Annotated[str, Query(min_length=2, max_length=100)],
    current_user: Annotated[User, Depends(require_role(min_role="User"))],
) -> DataResponse[list[str]]:
    """Proxy for VIAF AutoSuggest — returns a list of displayForm name strings."""
    names: list[str] = []
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
    ) as client:
        try:
            resp = await client.get(_VIAF_AUTOSUGGEST, params={"query": query})
            logger.info("viaf_autosuggest", query=query, status=resp.status_code, url=str(resp.url))
            resp.raise_for_status()
            payload = resp.json()
            results: list[dict] = payload.get("result") or []
            names = [r["displayForm"] for r in results if r.get("displayForm")]
            logger.info("viaf_autosuggest_ok", query=query, count=len(names))
        except httpx.HTTPStatusError as exc:
            logger.warning("viaf_autosuggest_http_error", query=query, status=exc.response.status_code)
        except httpx.RequestError as exc:
            logger.warning("viaf_autosuggest_request_error", query=query, error=str(exc))
        except (KeyError, ValueError) as exc:
            logger.warning("viaf_autosuggest_parse_error", query=query, error=str(exc))
    return DataResponse(data=names)
