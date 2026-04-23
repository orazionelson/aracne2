"""ROR public search client.

ROR v2 API shape (https://ror.readme.io/v2/reference/):

    GET https://api.ror.org/v2/organizations?query=<q>

Returns an object with ``items``. Each item carries:

- ``id`` — full ROR URI (``https://ror.org/03vek6s52``)
- ``names`` — list of ``{value, types}`` entries; the preferred display
  name has ``"ror_display"`` in its ``types``; other entries are
  aliases (``"alias"``), acronyms (``"acronym"``), or labels in
  non-English languages (``"label"``).
- ``types`` — list of institution categories
  (``"education"``, ``"healthcare"``, …).
- ``locations`` — list of ``{geonames_details: {country_name, ...}}``.

No authentication is required. ROR asks callers to be polite and not
abuse the endpoint; the plugin router applies slowapi as usual to
shield the upstream from editor misuse.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.ror.schemas import RorHit

logger = structlog.get_logger()

_SEARCH_URL = "https://api.ror.org/v2/organizations"
_TIMEOUT = 8.0


async def search(
    q: str, *, rows: int = 10, transport: httpx.AsyncBaseTransport | None = None
) -> list[RorHit]:
    """Return up to ``rows`` ROR records matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error) surfaces
    as an empty list so the editor UI degrades to "no results" rather
    than an error banner. The caller's slowapi decorator enforces rate
    limiting on this proxy.

    ROR v2 does not expose a ``rows`` parameter; it always returns 20
    items per page. We slice locally so the plugin contract matches
    the ORCID / Wikidata panels.
    """
    rows = max(1, min(rows, 25))
    params = {"query": q}
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-RorLookup/1.0",
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
        logger.warning("ror_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("ror_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("ror_search_parse_error", error=str(exc))
        return []

    items = payload.get("items") or []
    if not isinstance(items, list):
        return []

    hits: list[RorHit] = []
    for item in items[:rows]:
        if not isinstance(item, dict):
            continue
        hit = _item_to_hit(item)
        if hit is not None:
            hits.append(hit)
    return hits


def _item_to_hit(item: dict[str, Any]) -> RorHit | None:
    uri = item.get("id")
    if not isinstance(uri, str) or not uri.startswith("https://ror.org/"):
        return None
    ror_id = uri.removeprefix("https://ror.org/").strip("/")
    if not ror_id:
        return None

    display, aliases = _split_names(item.get("names") or [])
    if not display:
        # No usable display name — skip rather than show a blank row.
        return None

    return RorHit(
        ror_id=ror_id,
        uri=uri,
        name=display,
        aliases=aliases,
        country=_first_country(item.get("locations") or []),
        types=[t for t in (item.get("types") or []) if isinstance(t, str)],
    )


def _split_names(names: list[Any]) -> tuple[str | None, list[str]]:
    """Pick the ror_display name; collect the rest as aliases, de-duplicated.

    ROR v2 guarantees exactly one ror_display per organisation. If it
    is missing for any reason (bad data), fall back to the first plain
    label.
    """
    display: str | None = None
    fallback: str | None = None
    alias_seen: dict[str, None] = {}

    for entry in names:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        types = entry.get("types") or []
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if isinstance(types, list) and "ror_display" in types:
            display = value
            continue
        if fallback is None and isinstance(types, list) and "label" in types:
            fallback = value
        alias_seen.setdefault(value, None)

    picked = display or fallback
    # Aliases excludes the picked display name itself.
    aliases = [n for n in alias_seen if n != picked]
    return picked, aliases


def _first_country(locations: list[Any]) -> str | None:
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        details = loc.get("geonames_details")
        if isinstance(details, dict):
            name = details.get("country_name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None
