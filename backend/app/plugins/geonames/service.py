"""GeoNames place-search client — used by the editor-side plugin router.

Uses the same upstream endpoint as the core collection-create-form
proxy (``https://secure.geonames.org/searchJSON``) but returns a
richer payload including the numeric ``geonameId`` so the editor can
build a ``@ref`` URI.

Username comes from ``system_settings.geonames_username`` — single
source of truth shared with the core router. See
``app.services.geonames_auth``.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.geonames.schemas import GeonamesHit, UriFormat

logger = structlog.get_logger()

_SEARCH_URL = "https://secure.geonames.org/searchJSON"
_TIMEOUT = 8.0


def build_uri(geoname_id: str, url_format: UriFormat) -> str:
    """Build the canonical URI using the configured format.

    ``web`` — ``https://www.geonames.org/{id}`` — human-readable, lands
    on the place page. Default.
    ``sws`` — ``http://sws.geonames.org/{id}/`` — Semantic Web URI
    used in Linked Open Data contexts (this is the official RDF URI
    GeoNames itself serves as).
    """
    if url_format == "sws":
        return f"http://sws.geonames.org/{geoname_id}/"
    return f"https://www.geonames.org/{geoname_id}"


async def search(
    q: str,
    *,
    username: str,
    url_format: UriFormat,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[GeonamesHit]:
    """Return up to ``rows`` GeoNames populated-place hits matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error, quota
    exhaustion) surfaces as an empty list so the editor UI degrades
    to "no results" rather than an error banner. Quota errors are
    logged at warning level so operators can trace them.
    """
    rows = max(1, min(rows, 25))
    params = {
        "name_startsWith": q,
        "featureClass": "P",
        "maxRows": rows,
        "style": "medium",
        "username": username,
    }
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-GeonamesLookup/1.0",
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
        logger.warning("geonames_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("geonames_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("geonames_search_parse_error", error=str(exc))
        return []

    # GeoNames signals quota exhaustion via a top-level ``status.value``
    # even on HTTP 200 — treat it as a failed lookup.
    if isinstance(payload, dict) and "status" in payload:
        status = payload.get("status") or {}
        logger.warning(
            "geonames_search_quota_or_error",
            status_value=status.get("value") if isinstance(status, dict) else None,
            message=status.get("message") if isinstance(status, dict) else None,
        )
        return []

    items = payload.get("geonames") or []
    if not isinstance(items, list):
        return []

    hits: list[GeonamesHit] = []
    for row in items[:rows]:
        if not isinstance(row, dict):
            continue
        gid_raw = row.get("geonameId")
        if gid_raw is None:
            continue
        try:
            gid = str(int(gid_raw))
        except (TypeError, ValueError):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        region = (row.get("adminName1") or "").strip()
        country = (row.get("countryName") or "").strip()
        hits.append(
            GeonamesHit(
                geoname_id=gid,
                uri=build_uri(gid, url_format),
                display=_compose_display(name, region, country),
                name=name,
                region=region,
                country=country,
                feature_class=(row.get("fcl") or "P")[:1],
            )
        )
    return hits


def _compose_display(name: str, region: str, country: str) -> str:
    parts = [p for p in (name, region, country) if p and p != name]
    if not parts:
        return name
    return f"{name}, {', '.join(parts)}"
