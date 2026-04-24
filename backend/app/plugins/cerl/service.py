"""CERL Thesaurus search client.

Upstream::

    GET https://data.cerl.org/thesaurus/_search?query={q}&format=json&size={rows}

Response (abridged)::

    {
      "hits": {
        "total": 42,
        "hits": [
          {
            "_id": "cnp01283953",
            "_source": {
              "type": "cnp",
              "headingName": "Aldus Manutius",
              "variantNames": ["Manuzio, Aldo", "Manutio, Aldo"],
              "biographicalData": "ca. 1449–1515",
              "nameOfPlace": "Venice"
            }
          },
          ...
        ]
      }
    }

The ``_id`` field carries a prefix that indicates the type:

    cnp — person
    cnc — corporate body (Corporate Name, rare)
    cnl — place (location)
    cni — imprint / institution (publishing house, bookseller)

No authentication. The service is maintained by CERL on behalf of
European research libraries; rate limits are per-IP and tolerant.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.cerl.schemas import CerlHit, EntityKind

logger = structlog.get_logger()

_SEARCH_URL = "https://data.cerl.org/thesaurus/_search"
_TIMEOUT = 8.0

# Prefix → bucket.
_PREFIX_KIND: dict[str, EntityKind] = {
    "cnp": "person",
    "cnc": "corporate",
    "cnl": "place",
    "cni": "imprint",
}


async def search(
    q: str,
    *,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[CerlHit]:
    """Return up to ``rows`` CERL Thesaurus records matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error)
    surfaces as an empty list.
    """
    rows = max(1, min(rows, 25))
    params = {"query": q, "format": "json", "size": str(rows)}
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-CerlLookup/1.0",
    }

    kwargs: dict[str, Any] = {
        "timeout": _TIMEOUT,
        "follow_redirects": True,
        "headers": headers,
    }
    if transport is not None:
        kwargs["transport"] = transport

    try:
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(_SEARCH_URL, params=params)
    except httpx.RequestError as exc:
        logger.warning("cerl_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("cerl_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("cerl_search_parse_error", error=str(exc))
        return []

    # CERL wraps hits in hits.hits (Elasticsearch legacy).
    outer = payload.get("hits") or {}
    if not isinstance(outer, dict):
        return []
    inner = outer.get("hits") or []
    if not isinstance(inner, list):
        return []

    hits: list[CerlHit] = []
    for row in inner[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _row_to_hit(row: dict[str, Any]) -> CerlHit | None:
    cerl_id = row.get("_id")
    src = row.get("_source") or {}
    if not isinstance(cerl_id, str) or not cerl_id.strip():
        return None
    if not isinstance(src, dict):
        return None
    label = src.get("headingName") or src.get("name") or src.get("mainName")
    if not isinstance(label, str) or not label.strip():
        return None
    prefix = cerl_id[:3].lower()
    kind: EntityKind = _PREFIX_KIND.get(prefix, "other")
    return CerlHit(
        cerl_id=cerl_id.strip(),
        uri=f"https://data.cerl.org/thesaurus/{cerl_id.strip()}",
        label=label.strip(),
        detail=_compose_detail(src),
        kind=kind,
    )


def _compose_detail(src: dict[str, Any]) -> str:
    parts: list[str] = []
    bio = src.get("biographicalData")
    if isinstance(bio, str) and bio.strip():
        parts.append(bio.strip())
    place = src.get("nameOfPlace") or src.get("placeName")
    if isinstance(place, str) and place.strip():
        parts.append(place.strip())
    variants = src.get("variantNames") or []
    if isinstance(variants, list) and variants:
        pick = [v for v in variants[:2] if isinstance(v, str) and v.strip()]
        if pick:
            parts.append("aka " + ", ".join(pick))
    return " · ".join(parts)
