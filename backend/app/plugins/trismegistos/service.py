"""Trismegistos ID-resolver service.

Trismegistos publishes only ID-based resolvers, not a free-text
search API. The three paths the plugin exercises are:

- **Text** — ``GET /dataservices/texrelations/<id>[?source=<src>]``
  JSON list of single-key dicts:
  ``[{"TM_ID": ["9"]}, {"HGV": ["9a"]}, {"DDBDP": ["9"]}, ...]``.
  A soft-404 is ``{"Message": "This ID is not in our database."}``.
  Reverse lookup from a partner ID works via ``?source=<src>``.

- **Place** — ``GET /dataservices/georelations/<id>``. Same JSON
  shape; first key is ``TM_Geo_ID``. Same soft-404 envelope.

- **Person** — Trismegistos has **no** ``perrelations`` JSON
  endpoint (only ``rdf/per`` returning RDF/XML). The resolver
  therefore does not hit the network for persons: it validates the
  ID is numeric and composes the canonical URL. The editor can
  click through to the TM page for a visual sanity check.

All upstream errors fail soft — the caller receives ``None`` and the
panel renders a clean "not found" state.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from app.plugins.trismegistos.schemas import TmKind, TrismegistosHit

logger = structlog.get_logger()

_BASE = "https://www.trismegistos.org"
_TEXRELATIONS = f"{_BASE}/dataservices/texrelations"
_GEORELATIONS = f"{_BASE}/dataservices/georelations"
_TIMEOUT = 10.0

# TM IDs are numeric. Partner-project IDs (HGV "9a", DDBDP "pap.1234",
# PHI "12345") may mix letters, digits, dots, underscores, slashes.
# The whitelist is defensive: anything else is rejected without a
# network call so we never build a URL from untrusted input.
_ID_SAFE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
_TM_NUMERIC = re.compile(r"^[1-9][0-9]{0,9}$")


def _build_hit(
    *,
    kind: TmKind,
    tm_id: str,
    partners: dict[str, list[str]],
) -> TrismegistosHit:
    """Assemble a hit object; label falls back to ``TM {kind} {id}``
    when no partner provides a human-readable name."""
    label = _derive_label(kind, tm_id, partners)
    return TrismegistosHit(
        tm_id=tm_id,
        uri=f"{_BASE}/{kind}/{tm_id}",
        label=label,
        kind=kind,
        partners=partners,
    )


def _derive_label(
    kind: TmKind, tm_id: str, partners: dict[str, list[str]]
) -> str:
    """Pick a human-readable label from partner data if available.

    For places the Wikipedia partner gives an excellent slug
    ("Alexandria"); for texts an HGV or DDBDP reference is at least
    recognisable. Falls back to ``TM {kind} {id}``.
    """
    if kind == "place":
        wiki = partners.get("Wikipedia")
        if wiki:
            slug = str(wiki[0]).replace("_", " ").strip()
            if slug:
                return slug
    if kind == "text":
        for key in ("HGV", "DDBDP", "PHI", "EDH", "EDCS"):
            value = partners.get(key)
            if value:
                return f"{key} {value[0]}"
    return f"TM {kind} {tm_id}"


def _parse_relations_payload(payload: Any) -> dict[str, list[str]] | None:
    """Extract the ``{partner: [ids]}`` map from a relations response.

    Returns ``None`` when the response is the soft-404
    ``{"Message": "..."}`` envelope or is otherwise malformed.
    """
    if isinstance(payload, dict) and "Message" in payload:
        return None
    if not isinstance(payload, list):
        return None
    partners: dict[str, list[str]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if not isinstance(key, str):
                continue
            # Skip the self-reference rows (TM_ID / TM_Geo_ID).
            if key in ("TM_ID", "TM_Geo_ID"):
                continue
            if value is None:
                continue
            if isinstance(value, list):
                ids = [str(v) for v in value if v is not None and str(v).strip()]
                if ids:
                    partners[key] = ids
    return partners


def _extract_tm_id(payload: Any, self_key: str) -> str | None:
    """Pull the canonical TM id from a relations response.

    ``self_key`` is ``TM_ID`` for texts and ``TM_Geo_ID`` for places.
    """
    if not isinstance(payload, list):
        return None
    for item in payload:
        if isinstance(item, dict) and self_key in item:
            value = item[self_key]
            if isinstance(value, list) and value:
                candidate = str(value[0]).strip()
                if _TM_NUMERIC.match(candidate):
                    return candidate
    return None


async def _get_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Any | None:
    """GET *url* and return parsed JSON, or ``None`` on any hiccup."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-Trismegistos/2.0",
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
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        logger.warning("trismegistos_request_error", url=url, error=str(exc))
        return None
    if not resp.is_success:
        logger.warning("trismegistos_http_error", url=url, status=resp.status_code)
        return None
    try:
        return resp.json()
    except ValueError as exc:
        logger.warning("trismegistos_parse_error", url=url, error=str(exc))
        return None


# ── Public dispatcher ──────────────────────────────────────────────────────


async def resolve(
    *,
    kind: TmKind,
    identifier: str,
    source: str = "trismegistos",
    transport: httpx.AsyncBaseTransport | None = None,
) -> TrismegistosHit | None:
    """Resolve a Trismegistos ID and return the hit, or ``None``.

    ``source`` is honoured only for ``kind == "text"``. For persons
    and places the resolver never sends a source parameter.
    """
    ident = identifier.strip()
    if not ident or not _ID_SAFE.match(ident):
        return None

    if kind == "person":
        return await _resolve_person(ident)
    if kind == "place":
        return await _resolve_place(ident, transport=transport)
    return await _resolve_text(ident, source=source, transport=transport)


async def _resolve_person(identifier: str) -> TrismegistosHit | None:
    """Persons are resolved without a network call (no JSON endpoint)."""
    if not _TM_NUMERIC.match(identifier):
        return None
    return _build_hit(kind="person", tm_id=identifier, partners={})


async def _resolve_place(
    identifier: str, *, transport: httpx.AsyncBaseTransport | None = None,
) -> TrismegistosHit | None:
    if not _TM_NUMERIC.match(identifier):
        return None
    payload = await _get_json(
        f"{_GEORELATIONS}/{identifier}", transport=transport,
    )
    partners = _parse_relations_payload(payload)
    if partners is None:
        return None
    return _build_hit(kind="place", tm_id=identifier, partners=partners)


async def _resolve_text(
    identifier: str,
    *,
    source: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TrismegistosHit | None:
    params: dict[str, str] | None = None
    if source and source != "trismegistos":
        params = {"source": source}
    payload = await _get_json(
        f"{_TEXRELATIONS}/{identifier}",
        params=params,
        transport=transport,
    )
    partners = _parse_relations_payload(payload)
    if partners is None:
        return None
    # The canonical TM id lives inside the payload; for a direct TM
    # lookup the input and the response id agree, but a partner-ID
    # reverse-lookup needs the response-side id.
    tm_id = _extract_tm_id(payload, self_key="TM_ID")
    if tm_id is None:
        # Fallback: trust the input if it is a plain TM id.
        if source == "trismegistos" and _TM_NUMERIC.match(identifier):
            tm_id = identifier
        else:
            return None
    return _build_hit(kind="text", tm_id=tm_id, partners=partners)
