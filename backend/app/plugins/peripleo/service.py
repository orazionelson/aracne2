"""Peripleo search client.

Upstream::

    GET https://peripleo.pelagios.org/peripleo/search?q={q}&limit={rows}

Response (abridged)::

    {
      "total": 512,
      "took": 31,
      "items": [
        {
          "identifier": "https://pleiades.stoa.org/places/423025",
          "title": "Roma",
          "description": "Roman settlement — capital of the Roman empire",
          "dataset": {
            "id": "pleiades",
            "title": "Pleiades"
          },
          "geo_bounds": {...},
          ...
        },
        ...
      ]
    }

Peripleo's search API is public, no keys, no per-IP quota documented
— the plugin router still adds slowapi as a defensive measure.

Schema caveats: the public Peripleo is under active development and
its response shape has changed between major versions. The parser
tolerates missing / renamed fields and degrades to an empty list
rather than crashing. If a deployment observes the upstream shape
drifts, swap the endpoint URL to a pinned mirror without touching
the router or schemas.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.peripleo.schemas import PeripleoHit

logger = structlog.get_logger()

_SEARCH_URL = "https://peripleo.pelagios.org/peripleo/search"
_TIMEOUT = 10.0


async def search(
    q: str,
    *,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[PeripleoHit]:
    """Return up to ``rows`` Peripleo place hits for ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error)
    surfaces as an empty list.
    """
    rows = max(1, min(rows, 25))
    params = {"q": q, "limit": str(rows)}
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-PeripleoLookup/1.0",
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
        logger.warning("peripleo_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("peripleo_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("peripleo_search_parse_error", error=str(exc))
        return []

    items = payload.get("items") or payload.get("hits") or []
    if not isinstance(items, list):
        return []

    hits: list[PeripleoHit] = []
    for row in items[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _row_to_hit(row: dict[str, Any]) -> PeripleoHit | None:
    # The identifier carries the canonical gazetteer URI. Different
    # Peripleo versions have named it "identifier" or "id" or "uri" —
    # accept any of them.
    uri = row.get("identifier") or row.get("uri") or row.get("id")
    if not isinstance(uri, str) or not uri.startswith(("http://", "https://")):
        return None

    label = row.get("title") or row.get("label") or row.get("name")
    if not isinstance(label, str) or not label.strip():
        return None

    # Source dataset name.
    dataset = row.get("dataset")
    source = ""
    if isinstance(dataset, dict):
        source = str(dataset.get("title") or dataset.get("id") or "").strip()
    elif isinstance(dataset, str):
        source = dataset.strip()

    desc = row.get("description") or row.get("type") or row.get("placetype") or ""
    if isinstance(desc, list):
        desc = ", ".join(str(d) for d in desc if isinstance(d, str))
    if not isinstance(desc, str):
        desc = ""

    return PeripleoHit(
        uri=uri,
        label=label.strip(),
        source=source or _infer_source(uri),
        detail=desc.strip(),
    )


def _infer_source(uri: str) -> str:
    """When Peripleo omits the dataset name, guess from the URI host."""
    if "pleiades.stoa.org" in uri:
        return "Pleiades"
    if "gazetteer.dainst.org" in uri:
        return "iDAI.gazetteer"
    if "chronontology.dainst.org" in uri:
        return "ChronOntology"
    if "topostext.org" in uri:
        return "ToposText"
    if "vici.org" in uri:
        return "Vici"
    return ""
