"""Wikidata search proxy.

Thin proxy over the public ``wbsearchentities`` endpoint. Used by the TEI
editor to let an editor resolve a ``<persName>`` / ``<placeName>`` /
``<orgName>`` selection to a canonical Wikidata URI, stored as ``@ref`` on
the TEI element.

Design mirrors :mod:`app.routers.viaf` and :mod:`app.routers.geonames`:

- authenticated (any role) — keeps unauthenticated load off the upstream;
- rate-limited (30/min) per IP via the shared slowapi limiter;
- fail-soft: upstream failures degrade to an empty list so the editor UI
  does not error out when Wikidata has a hiccup;
- no SSRF risk: the URL is a hard-coded Wikidata endpoint, never derived
  from user input.
"""

from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, Query, Request

from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.wikidata import WikidataHit

router = APIRouter(prefix="/wikidata", tags=["wikidata"])

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_TIMEOUT = 8.0
_HEADERS = {
    "User-Agent": "Aracne2/1.0 (TEI CMS; https://github.com/orazionelson/aracne2)",
    "Accept": "application/json",
}

logger = structlog.get_logger()


@router.get("/search")
@limiter.limit("30/minute")
async def wikidata_search(
    request: Request,
    current_user: Annotated[User, Depends(require_role(min_role="User"))],
    q: Annotated[str, Query(min_length=2, max_length=200, alias="q")],
    lang: Annotated[str, Query(min_length=2, max_length=8, pattern=r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")] = "it",
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> DataResponse[list[WikidataHit]]:
    """Search Wikidata entities matching *q* in the given *lang*.

    Returns up to *limit* hits, each with its canonical URI ready to be
    used as a TEI ``@ref`` value. When the upstream call fails for any
    reason the response degrades gracefully to ``data: []`` — the editor
    UI treats that as "no results", no disruptive error surfaces.
    """
    hits: list[WikidataHit] = []
    params = {
        "action": "wbsearchentities",
        "search": q,
        "language": lang,
        "format": "json",
        "type": "item",
        "limit": str(limit),
    }
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS
    ) as client:
        try:
            resp = await client.get(_WIKIDATA_API, params=params)
            logger.info("wikidata_search", status=resp.status_code, q=q, lang=lang)
            resp.raise_for_status()
            payload = resp.json()
            results: list[dict] = payload.get("search") or []
            for row in results:
                qid = row.get("id")
                label = row.get("label") or row.get("title")
                uri = row.get("concepturi")
                if not (qid and label and uri):
                    continue
                hits.append(
                    WikidataHit(
                        qid=qid,
                        label=label,
                        description=row.get("description"),
                        uri=uri,
                    )
                )
            logger.info("wikidata_search_ok", count=len(hits))
        except httpx.HTTPStatusError as exc:
            logger.warning("wikidata_search_http_error", status=exc.response.status_code)
        except httpx.RequestError as exc:
            logger.warning("wikidata_search_request_error", error=str(exc))
        except (KeyError, ValueError) as exc:
            logger.warning("wikidata_search_parse_error", error=str(exc))
    return DataResponse(data=hits)
