"""lobid.org GND search client.

Upstream::

    GET https://lobid.org/gnd/search?q={q}&format=json&size={rows}

Response (abridged)::

    {
      "totalItems": 42,
      "member": [
        {
          "id": "https://d-nb.info/gnd/118524534",
          "gndIdentifier": "118524534",
          "preferredName": "Goethe, Johann Wolfgang von",
          "type": [
            "https://d-nb.info/standards/elementset/gnd#DifferentiatedPerson",
            "https://d-nb.info/standards/elementset/gnd#Person",
            "https://d-nb.info/standards/elementset/gnd#AuthorityResource"
          ],
          "dateOfBirth": ["1749"],
          "dateOfDeath": ["1832"],
          "professionOrOccupation": [{"label": "Schriftsteller"}],
          ...
        }
      ]
    }

No authentication, no per-key quotas. The public API is maintained by
hbz for the German library community; rate limits are per-IP and
tolerant. The plugin router adds slowapi on top.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.gnd.schemas import EntityKind, GndHit

logger = structlog.get_logger()

_SEARCH_URL = "https://lobid.org/gnd/search"
_TIMEOUT = 8.0

# Map from lobid's "type" URIs (the fragment after "gnd#") to our
# coarse bucket. First match wins — the order of _TYPE_PRIORITY below
# decides which bucket an entry with multiple types ends up in.
_TYPE_PRIORITY: list[tuple[str, EntityKind]] = [
    ("DifferentiatedPerson", "person"),
    ("Person", "person"),
    ("Pseudonym", "person"),
    ("RoyalOrMemberOfARoyalHouse", "person"),
    ("CorporateBody", "corporate"),
    ("ReligiousCorporateBody", "corporate"),
    ("OrganOfCorporateBody", "corporate"),
    ("Company", "corporate"),
    ("PlaceOrGeographicName", "place"),
    ("TerritorialCorporateBodyOrAdministrativeUnit", "place"),
    ("Country", "place"),
    ("Work", "work"),
    ("MusicalWork", "work"),
    ("SubjectHeading", "subject"),
    ("SubjectHeadingSensoStricto", "subject"),
]


async def search(
    q: str,
    *,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[GndHit]:
    """Return up to ``rows`` GND records matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error) surfaces
    as an empty list so the editor UI degrades to "no results" rather
    than an error banner.
    """
    rows = max(1, min(rows, 25))
    params = {"q": q, "format": "json", "size": str(rows)}
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-GndLookup/1.0",
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
        logger.warning("gnd_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("gnd_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("gnd_search_parse_error", error=str(exc))
        return []

    items = payload.get("member") or []
    if not isinstance(items, list):
        return []

    hits: list[GndHit] = []
    for row in items[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _row_to_hit(row: dict[str, Any]) -> GndHit | None:
    gnd_id = row.get("gndIdentifier")
    uri = row.get("id")
    label = row.get("preferredName")
    if not isinstance(gnd_id, str) or not gnd_id.strip():
        return None
    if not isinstance(uri, str) or not uri.startswith("https://d-nb.info/gnd/"):
        return None
    if not isinstance(label, str) or not label.strip():
        return None
    return GndHit(
        gnd_id=gnd_id.strip(),
        uri=uri,
        label=label.strip(),
        detail=_compose_detail(row),
        kind=_classify(row.get("type") or []),
    )


def _compose_detail(row: dict[str, Any]) -> str:
    """Build a short disambiguator: dates, profession, or place name."""
    parts: list[str] = []
    dob = _first_string(row.get("dateOfBirth") or [])
    dod = _first_string(row.get("dateOfDeath") or [])
    if dob or dod:
        parts.append(f"{dob or '?'}–{dod or '?'}")
    prof = row.get("professionOrOccupation") or []
    if isinstance(prof, list):
        labels = [
            p.get("label") for p in prof
            if isinstance(p, dict) and isinstance(p.get("label"), str)
        ]
        if labels:
            parts.append(", ".join(labels[:2]))
    # Places carry placeOfBirth / placeOfDeath / geographicAreaCode;
    # the label of an associated place is often enough.
    place = row.get("placeOfBirth") or row.get("geographicAreaCode") or []
    if isinstance(place, list):
        for p in place:
            if isinstance(p, dict) and isinstance(p.get("label"), str):
                parts.append(p["label"])
                break
    return " · ".join(parts)


def _first_string(seq: list[Any]) -> str:
    for item in seq:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def _classify(types: list[Any]) -> EntityKind:
    """Pick a bucket from lobid's list of gnd#XXX type URIs."""
    if not isinstance(types, list):
        return "other"
    # Each entry is typically a URI like
    # "https://d-nb.info/standards/elementset/gnd#DifferentiatedPerson".
    suffixes = [t.rsplit("#", 1)[-1] for t in types if isinstance(t, str)]
    for fragment, bucket in _TYPE_PRIORITY:
        if fragment in suffixes:
            return bucket
    return "other"
