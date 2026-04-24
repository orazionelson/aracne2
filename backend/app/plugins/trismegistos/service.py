"""Trismegistos search client.

TM exposes an ``api.trismegistos.org`` family of endpoints, one per
kind of record (persons, places, texts, archives, authors, …). The
service queries persons, places, and texts in parallel so the editor
panel can show a unified hit list.

Schema caveats: TM's API has changed across versions (v1, v2, the
current "api.trismegistos.org/v3"). The parser reads defensively and
accepts several field-name variants. **Verify the upstream shape at
first activation** — if the real response differs, tune the parser
and the URL template without touching router / schemas.

Auth: TM's current freemium tier requires an API key sent via the
``Authorization: Bearer`` header for any non-trivial query. An empty
key short-circuits to an empty result list (and the router surfaces
a 503 with a clear code so the frontend can render a banner).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.trismegistos.schemas import TmKind, TrismegistosHit

logger = structlog.get_logger()

_SEARCH_URL = "https://www.trismegistos.org/api/v3/search"
_TIMEOUT = 10.0


async def search(
    q: str,
    *,
    api_key: str,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[TrismegistosHit]:
    """Return up to ``rows`` TM hits across persons/places/texts.

    Raises no error on an empty ``api_key`` — returns ``[]``. The
    router decides to surface a 503 with ``TMG_API_KEY_MISSING``
    when that happens.

    Fail-soft on any upstream problem (timeout, 5xx, parse error).
    """
    if not api_key.strip():
        return []

    rows = max(1, min(rows, 25))
    params = {"q": q, "rows": str(rows)}
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key.strip()}",
        "User-Agent": "Aracne2-Trismegistos/1.0",
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
        logger.warning("trismegistos_search_request_error", error=str(exc))
        return []

    if resp.status_code == 401:
        logger.warning("trismegistos_search_unauthorized")
        return []
    if not resp.is_success:
        logger.warning("trismegistos_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("trismegistos_search_parse_error", error=str(exc))
        return []

    items = _extract_items(payload)
    hits: list[TrismegistosHit] = []
    for row in items[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _extract_items(payload: Any) -> list[Any]:
    """Accept the half-dozen envelope shapes TM has used."""
    if not isinstance(payload, dict):
        return []
    for key in ("results", "hits", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for inner_key in ("hits", "items", "data"):
                inner = value.get(inner_key)
                if isinstance(inner, list):
                    return inner
    return []


def _row_to_hit(row: dict[str, Any]) -> TrismegistosHit | None:
    # Accept any of the id fields TM has used.
    tm_id_raw = row.get("tm_id") or row.get("id") or row.get("tmId") or row.get("identifier")
    if tm_id_raw is None:
        return None
    try:
        tm_id = str(int(str(tm_id_raw)))
    except (TypeError, ValueError):
        return None

    kind = _classify(row)
    if kind is None:
        return None

    label = (
        row.get("name")
        or row.get("label")
        or row.get("title")
        or row.get("display_name")
    )
    if not isinstance(label, str) or not label.strip():
        return None

    uri = f"https://www.trismegistos.org/{kind}/{tm_id}"
    return TrismegistosHit(
        tm_id=tm_id,
        uri=uri,
        label=label.strip(),
        detail=_compose_detail(row),
        kind=kind,
    )


def _classify(row: dict[str, Any]) -> TmKind | None:
    """Pick a bucket based on the ``type`` or ``category`` field."""
    t = str(
        row.get("type")
        or row.get("category")
        or row.get("entity_type")
        or ""
    ).lower()
    if t in ("person", "people", "persons"):
        return "person"
    if t in ("place", "places"):
        return "place"
    if t in ("text", "texts"):
        return "text"
    # Fallback: if an URL / link field hints at the type, use it.
    for key in ("url", "link", "self"):
        value = row.get(key)
        if isinstance(value, str):
            if "/person/" in value:
                return "person"
            if "/place/" in value:
                return "place"
            if "/text/" in value:
                return "text"
    return None


def _compose_detail(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("dates", "date_range", "period", "provenance", "genre", "language"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            pick = [v for v in value if isinstance(v, str) and v.strip()]
            if pick:
                parts.append(", ".join(pick[:2]))
        if len(parts) >= 2:
            break
    return " · ".join(parts)
