"""VIAF AutoSuggest client — used by the editor-side plugin router.

VIAF AutoSuggest response shape::

    GET https://viaf.org/viaf/AutoSuggest?query=dante

    {
      "result": [
        {
          "displayForm": "Alighieri, Dante, 1265-1321",
          "nametype": "personal",
          "viafid": "27063124",
          "term": "...",
          "recordID": "..."
        },
        ...
      ]
    }

No authentication required. Rate limits are per-IP and loose but the
plugin router adds slowapi on top to shield the upstream from editor
misuse.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.viaf.schemas import ViafHit

logger = structlog.get_logger()

_AUTOSUGGEST_URL = "https://viaf.org/viaf/AutoSuggest"
_TIMEOUT = 8.0


async def search(
    q: str,
    *,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[ViafHit]:
    """Return up to ``rows`` VIAF AutoSuggest hits matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error) surfaces
    as an empty list so the editor UI degrades to "no results" rather
    than an error banner.
    """
    rows = max(1, min(rows, 25))
    params = {"query": q}
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-ViafLookup/1.0",
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
            resp = await client.get(_AUTOSUGGEST_URL, params=params)
    except httpx.RequestError as exc:
        logger.warning("viaf_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("viaf_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("viaf_search_parse_error", error=str(exc))
        return []

    results = payload.get("result") or []
    if not isinstance(results, list):
        return []

    hits: list[ViafHit] = []
    for row in results[:rows]:
        if not isinstance(row, dict):
            continue
        viaf_id = row.get("viafid")
        display = row.get("displayForm")
        if not isinstance(viaf_id, str) or not viaf_id.strip():
            continue
        if not isinstance(display, str) or not display.strip():
            continue
        name_type = row.get("nametype") or ""
        if not isinstance(name_type, str):
            name_type = ""
        vid = viaf_id.strip()
        hits.append(
            ViafHit(
                viaf_id=vid,
                uri=f"http://viaf.org/viaf/{vid}",
                display=display.strip(),
                name_type=name_type.strip().lower(),
            )
        )
    return hits
