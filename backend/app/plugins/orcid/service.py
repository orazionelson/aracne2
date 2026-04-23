"""ORCID public search client.

Uses the **expanded-search** endpoint
(https://pub.orcid.org/v3.0/expanded-search/) rather than the bare
``search`` endpoint, because expanded-search returns display names and
affiliation snippets inline — sparing the plugin from N+1 round-trips
to ``/{orcid}/record`` just to show a useful hit list.

No authentication is required for the public ORCID API. Rate limits
are unpublished; the plugin router applies the platform's usual
slowapi cap so editor misuse cannot exhaust shared goodwill.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.plugins.orcid.schemas import OrcidHit

logger = structlog.get_logger()

_SEARCH_URL = "https://pub.orcid.org/v3.0/expanded-search/"
_TIMEOUT = 8.0


async def search(
    q: str, *, rows: int = 10, transport: httpx.AsyncBaseTransport | None = None
) -> list[OrcidHit]:
    """Return up to ``rows`` ORCID records matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error) surfaces
    as an empty list so the editor UI degrades to "no results" rather
    than an error banner. The caller's slowapi decorator already
    enforces rate limiting on this proxy.
    """
    rows = max(1, min(rows, 25))  # pub.orcid.org caps around 200; editors never need more than 25
    params = {"q": q, "rows": str(rows)}
    headers = {
        "Accept": "application/json",
        "User-Agent": "Aracne2-OrcidSearch/1.0",
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
        logger.warning("orcid_search_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("orcid_search_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("orcid_search_parse_error", error=str(exc))
        return []

    results = payload.get("expanded-result") or []
    if not isinstance(results, list):
        return []

    hits: list[OrcidHit] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        orcid_id = row.get("orcid-id")
        if not isinstance(orcid_id, str) or not orcid_id.strip():
            continue
        hit = OrcidHit(
            orcid=orcid_id.strip(),
            uri=f"https://orcid.org/{orcid_id.strip()}",
            given_names=_maybe_str(row.get("given-names")),
            family_name=_maybe_str(row.get("family-names")),
            credit_name=_maybe_str(row.get("credit-name")),
            affiliations=_affiliations(row),
        )
        hits.append(hit)
    return hits


def _maybe_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _affiliations(row: dict[str, Any]) -> list[str]:
    """Extract institution names from the ``institution-name`` field.

    The expanded-search endpoint returns institutions as a flat list of
    strings in ``institution-name``. We de-duplicate while preserving
    first-seen order (dict.fromkeys trick).
    """
    names = row.get("institution-name") or []
    if not isinstance(names, list):
        return []
    clean = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    return list(dict.fromkeys(clean))
