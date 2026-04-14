from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.config import settings
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.common import DataResponse

router = APIRouter(prefix="/geonames", tags=["geonames"])

_GEONAMES_SEARCH = "https://secure.geonames.org/searchJSON"
_TIMEOUT = 8.0
_HEADERS = {
    "User-Agent": "Aracne2/1.0 (TEI CMS; https://github.com/orazionelson/aracne2)",
    "Accept": "application/json",
}

logger = structlog.get_logger()


class GeonamesPlace(BaseModel):
    name: str
    region: str
    country: str
    geonames_id: int


@router.get("/search")
@limiter.limit("30/minute")
async def geonames_search(
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    current_user: Annotated[User, Depends(require_role(min_role="User"))],
) -> DataResponse[list[GeonamesPlace]]:
    """Proxy for GeoNames searchJSON — returns populated places matching *q*.

    Results are limited to ``featureClass=P`` (populated places) and capped at
    10 rows.  The GeoNames username is read from ``settings.geonames_username``.
    On any upstream error the endpoint returns an empty list rather than failing,
    so the UI degrades gracefully to a plain text input.
    """
    places: list[GeonamesPlace] = []
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
    ) as client:
        try:
            resp = await client.get(
                _GEONAMES_SEARCH,
                params={
                    "name_startsWith": q,
                    "featureClass": "P",
                    "maxRows": 10,
                    "style": "medium",
                    "username": settings.geonames_username,
                },
            )
            logger.info("geonames_search", status=resp.status_code)
            resp.raise_for_status()
            payload = resp.json()
            for item in payload.get("geonames") or []:
                places.append(
                    GeonamesPlace(
                        name=item.get("name", ""),
                        region=item.get("adminName1", ""),
                        country=item.get("countryName", ""),
                        geonames_id=int(item.get("geonameId", 0)),
                    )
                )
            logger.info("geonames_search_ok", count=len(places))
        except httpx.HTTPStatusError as exc:
            logger.warning("geonames_search_http_error", status=exc.response.status_code)
        except httpx.RequestError as exc:
            logger.warning("geonames_search_request_error", error=str(exc))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("geonames_search_parse_error", error=str(exc))
    return DataResponse(data=places)
