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

    # CERL serves two response shapes from the same endpoint:
    #
    #   • Legacy Elasticsearch wrapping: ``{ "hits": { "hits": [ {"_id": …,
    #     "_source": {...}}, … ] } }``
    #   • Current CERL Thesaurus shape (observed live, 2026): ``{ "rows":
    #     [ {"id": …, "name_display_line": …, "type": "cnp", …}, … ],
    #     "hits": { "value": …, "relation": "eq" } }``
    #
    # ``hits.hits`` returned empty against the second shape, leaving us to
    # log "no records" while a direct browser call to data.cerl.org listed
    # plenty. Honour both shapes; pick the one that actually carries data.
    rows_list: list[Any] = []
    legacy = payload.get("hits")
    if isinstance(legacy, dict):
        inner = legacy.get("hits")
        if isinstance(inner, list) and inner:
            rows_list = inner
    if not rows_list:
        modern = payload.get("rows")
        if isinstance(modern, list):
            rows_list = modern

    hits: list[CerlHit] = []
    for row in rows_list[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _row_to_hit(row: dict[str, Any]) -> CerlHit | None:
    """Project either response flavour into a CerlHit.

    Legacy Elasticsearch: id at ``_id``, fields nested under ``_source``.
    Modern CERL: id at ``id`` (top-level), fields flat on the row,
    extra metadata mirrored under ``data``.
    """
    cerl_id = row.get("_id") or row.get("id")
    if not isinstance(cerl_id, str) or not cerl_id.strip():
        return None
    src = row.get("_source")
    if not isinstance(src, dict):
        # Modern shape — the row itself is the source of truth.
        src = row

    label = (
        src.get("headingName")
        or src.get("name_display_line")
        or src.get("mainName")
    )
    # Some modern rows carry only the typed-name lists.
    if not isinstance(label, str) or not label.strip():
        for key in ("personalName", "imprintName", "corporateName", "placeName"):
            value = src.get(key)
            if isinstance(value, list) and value and isinstance(value[0], str):
                label = value[0]
                break
            if isinstance(value, str) and value.strip():
                label = value
                break
    if not isinstance(label, str) or not label.strip():
        return None

    prefix = cerl_id[:3].lower()
    # The modern row also carries a ``type`` (``cnp`` / ``cnc`` / …) we
    # can use as a fallback when the prefix is missing or malformed.
    kind: EntityKind = _PREFIX_KIND.get(prefix, "other")
    if kind == "other":
        type_hint = row.get("type") or src.get("type")
        if isinstance(type_hint, str):
            kind = _PREFIX_KIND.get(type_hint.lower()[:3], "other")
    return CerlHit(
        cerl_id=cerl_id.strip(),
        uri=f"https://data.cerl.org/thesaurus/{cerl_id.strip()}",
        label=label.strip(),
        detail=_compose_detail(src),
        kind=kind,
    )


def _compose_detail(src: dict[str, Any]) -> str:
    parts: list[str] = []
    # Legacy field — keep working for the test fixtures that mirror
    # the old shape and any CERL endpoint still serving it.
    bio = src.get("biographicalData")
    if isinstance(bio, str) and bio.strip():
        parts.append(bio.strip())
    # Modern shape — bio dates live under ``additional_display_line``
    # (e.g. "1740-1817 Priester") which combines lifespan + role.
    add = src.get("additional_display_line")
    if isinstance(add, str) and add.strip() and add.strip() not in parts:
        parts.append(add.strip())
    # Place — legacy keys first, then modern ``address`` (list of
    # toponyms; first entry is canonical).
    place = src.get("nameOfPlace") or src.get("placeName")
    if isinstance(place, str) and place.strip():
        parts.append(place.strip())
    elif isinstance(src.get("address"), list):
        for value in src["address"]:
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
                break
    # Variants — legacy ``variantNames`` and modern flat name lists
    # (``personalName`` etc.).
    variants_raw: list[Any] = []
    leg = src.get("variantNames")
    if isinstance(leg, list):
        variants_raw.extend(leg)
    for key in ("personalName", "imprintName", "corporateName"):
        modern = src.get(key)
        if isinstance(modern, list):
            # Skip the first entry — it is the heading we already
            # rendered as the hit's label.
            variants_raw.extend(modern[1:])
    pick = [v for v in variants_raw[:3] if isinstance(v, str) and v.strip()]
    if pick:
        parts.append("aka " + ", ".join(pick))
    return " · ".join(parts)
