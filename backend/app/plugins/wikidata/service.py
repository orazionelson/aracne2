"""Wikidata search client — wraps ``wbsearchentities``.

Public endpoint, no authentication, no per-key quotas. Rate limits
live with Wikidata (they cap aggressive clients via HTTP 429) and
the plugin router adds slowapi on top to shield the upstream from
editor misuse.

Fail-soft: any upstream problem (timeout, 5xx, parse error) surfaces
as an empty list so the editor UI degrades to "no results" rather
than an error banner.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.wikidata.schemas import WikidataHit

logger = structlog.get_logger()

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_TIMEOUT = 8.0


async def search(
    q: str,
    *,
    lang: str = "it",
    limit: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[WikidataHit]:
    """Return up to ``limit`` Wikidata entity hits for ``q`` in ``lang``.

    Drops rows that are missing any of the three fields the editor
    relies on (``qid``, ``label``, ``concepturi``) — we never emit
    half-records because the TEI ``@ref`` would be empty.
    """
    limit = max(1, min(limit, 25))
    params = {
        "action": "wbsearchentities",
        "search": q,
        "language": lang,
        "format": "json",
        "type": "item",
        "limit": str(limit),
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-WikidataLookup/1.0",
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
            resp = await client.get(_WIKIDATA_API, params=params)
    except httpx.RequestError as exc:
        logger.warning("wikidata_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("wikidata_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("wikidata_search_parse_error", error=str(exc))
        return []

    results = payload.get("search") or []
    if not isinstance(results, list):
        return []

    hits: list[WikidataHit] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        qid = row.get("id")
        label = row.get("label") or row.get("title")
        uri = row.get("concepturi")
        if not (isinstance(qid, str) and isinstance(label, str) and isinstance(uri, str)):
            continue
        if not qid.strip() or not label.strip() or not uri.strip():
            continue
        hits.append(
            WikidataHit(
                qid=qid,
                label=label,
                description=row.get("description") or None,
                uri=uri,
            )
        )
    return hits
