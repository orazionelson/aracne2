"""Getty AAT SPARQL search client.

Upstream::

    GET https://vocab.getty.edu/sparql.json?query=<urlencoded-sparql>

SPARQL template (uses Getty's ``luc:term`` Lucene extension for fast
substring matching on labels)::

    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX aat: <http://vocab.getty.edu/aat/>
    PREFIX luc: <http://www.ontotext.com/owlim/lucene#>
    PREFIX gvp: <http://vocab.getty.edu/ontology#>

    SELECT ?uri ?label ?scope WHERE {
      ?uri skos:inScheme aat: ;
           luc:term "oil*" ;
           gvp:prefLabelGVP [xl:literalForm ?label] .
      FILTER(LANG(?label) = "en")
      OPTIONAL {
        ?uri skos:scopeNote [dct:language gvp_lang:en ; rdf:value ?scope]
      }
    }
    LIMIT 10

The response shape is the standard SPARQL-JSON binding::

    {
      "head": {"vars": ["uri", "label", "scope"]},
      "results": {
        "bindings": [
          {
            "uri":   {"type": "uri",     "value": "http://vocab.getty.edu/aat/300015050"},
            "label": {"type": "literal", "value": "oil paint", "xml:lang": "en"},
            "scope": {"type": "literal", "value": "Pigment mixed with a drying oil ..."}
          },
          ...
        ]
      }
    }

Upstream has no authentication. The SPARQL endpoint honours a public
rate limit; the plugin router adds slowapi as a defensive cap.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from app.plugins.getty_aat.schemas import GettyAatHit

logger = structlog.get_logger()

_SPARQL_URL = "https://vocab.getty.edu/sparql.json"
_TIMEOUT = 10.0

# Match bare ASCII-ish word chars + hyphens for the luc:term expression
# — everything else we drop to stay inside Getty's Lucene grammar.
_LUCENE_SAFE = re.compile(r"[^A-Za-z0-9 _-]+")


def _build_query(term: str, limit: int) -> str:
    """Build the SPARQL query string.

    ``term`` is sanitised down to safe Lucene characters and a trailing
    ``*`` is appended so users typing "oil" find "oil paint", "oil
    painting", etc.
    """
    safe = _LUCENE_SAFE.sub("", term).strip()
    if not safe:
        safe = "a"  # dummy, will return nothing meaningful — caller will ignore
    lucene = safe + "*"
    # Embedded as a quoted literal inside the query. The safe pattern
    # guarantees no embedded quote character can escape.
    return (
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
        "PREFIX aat: <http://vocab.getty.edu/aat/> "
        "PREFIX luc: <http://www.ontotext.com/owlim/lucene#> "
        "PREFIX gvp: <http://vocab.getty.edu/ontology#> "
        "PREFIX xl: <http://www.w3.org/2008/05/skos-xl#> "
        "PREFIX dct: <http://purl.org/dc/terms/> "
        "PREFIX gvp_lang: <http://vocab.getty.edu/language/> "
        "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
        "SELECT ?uri ?label ?scope WHERE { "
        "  ?uri skos:inScheme aat: ; "
        f'       luc:term "{lucene}" ; '
        "       gvp:prefLabelGVP [ xl:literalForm ?label ] . "
        '  FILTER(LANG(?label) = "en") '
        "  OPTIONAL { "
        "    ?uri skos:scopeNote [ dct:language gvp_lang:en ; rdf:value ?scope ] "
        "  } "
        "} "
        f"LIMIT {limit}"
    )


async def search(
    q: str,
    *,
    rows: int = 10,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[GettyAatHit]:
    """Return up to ``rows`` AAT concept hits matching ``q``.

    Fail-soft: any upstream problem (timeout, 5xx, parse error)
    surfaces as an empty list.
    """
    rows = max(1, min(rows, 25))
    query = _build_query(q, rows)
    params = {"query": query}
    headers = {
        "Accept": "application/sparql-results+json, application/json",
        "User-Agent": "Aracne2-GettyAAT/1.0",
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
            resp = await client.get(_SPARQL_URL, params=params)
    except httpx.RequestError as exc:
        logger.warning("getty_aat_request_error", error=str(exc))
        return []

    if not resp.is_success:
        logger.warning("getty_aat_http_error", status=resp.status_code)
        return []

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.warning("getty_aat_parse_error", error=str(exc))
        return []

    bindings = (
        payload.get("results", {}).get("bindings")
        if isinstance(payload, dict) else None
    )
    if not isinstance(bindings, list):
        return []

    hits: list[GettyAatHit] = []
    for row in bindings[:rows]:
        if not isinstance(row, dict):
            continue
        hit = _row_to_hit(row)
        if hit is not None:
            hits.append(hit)
    return hits


def _row_to_hit(row: dict[str, Any]) -> GettyAatHit | None:
    uri = _get_binding_value(row.get("uri"))
    label = _get_binding_value(row.get("label"))
    scope = _get_binding_value(row.get("scope"))
    if not uri or not label:
        return None
    if not uri.startswith("http://vocab.getty.edu/aat/"):
        return None
    aat_id = uri.rsplit("/", 1)[-1]
    if not aat_id.isdigit():
        return None
    return GettyAatHit(
        aat_id=aat_id,
        uri=uri,
        label=label.strip(),
        scope_note=scope.strip() if scope else "",
    )


def _get_binding_value(binding: Any) -> str:
    """Safely pull a SPARQL binding's ``.value`` field, returning ``""``
    if the shape is unexpected."""
    if not isinstance(binding, dict):
        return ""
    value = binding.get("value")
    if isinstance(value, str):
        return value
    return ""
