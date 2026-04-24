"""Getty AAT SPARQL service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.getty_aat.service import _build_query, search


def _oil_paint_binding() -> dict[str, object]:
    return {
        "uri": {"type": "uri", "value": "http://vocab.getty.edu/aat/300015050"},
        "label": {"type": "literal", "value": "oil paint", "xml:lang": "en"},
        "scope": {
            "type": "literal",
            "value": "Pigment mixed with a drying oil as the vehicle.",
        },
    }


def _painted_binding() -> dict[str, object]:
    return {
        "uri": {"type": "uri", "value": "http://vocab.getty.edu/aat/300054216"},
        "label": {"type": "literal", "value": "painting (image-making)"},
        # Sometimes scopeNote is missing
    }


# ── Query builder ───────────────────────────────────────────────────────────


def test_build_query_contains_lucene_wildcard() -> None:
    q = _build_query("oil", 5)
    assert 'luc:term "oil*"' in q
    assert "LIMIT 5" in q


def test_build_query_sanitises_dangerous_chars() -> None:
    """Quote / backslash injected into the user term must never survive
    into the Lucene literal — otherwise a carefully crafted query
    could break out of the embedded string and reshape the SPARQL."""
    q = _build_query('foo" bar \\ baz', 10)
    # Extract exactly the Lucene literal (between 'luc:term "' and its
    # closing '"'). The builder emits a single literal on the line.
    prefix = 'luc:term "'
    start = q.find(prefix) + len(prefix)
    end = q.find('"', start)
    literal = q[start:end]
    assert '"' not in literal
    assert "\\" not in literal
    assert literal.endswith("*")
    # The sanitiser keeps only alphanum + spaces + hyphens + underscores.
    assert all(c.isalnum() or c in " _-*" for c in literal)


# ── Search ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_parses_binding() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "head": {"vars": ["uri", "label", "scope"]},
                "results": {"bindings": [_oil_paint_binding()]},
            },
        )

    hits = await search("oil", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.aat_id == "300015050"
    assert hit.uri == "http://vocab.getty.edu/aat/300015050"
    assert hit.label == "oil paint"
    assert hit.scope_note.startswith("Pigment mixed with a drying oil")
    # The request hit the sparql.json endpoint.
    assert "vocab.getty.edu/sparql.json" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_handles_missing_scope() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": {"bindings": [_painted_binding()]}},
        )

    hits = await search("paint", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].scope_note == ""


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        bindings = [
            {
                "uri": {"type": "uri", "value": f"http://vocab.getty.edu/aat/{300000000 + i}"},
                "label": {"type": "literal", "value": f"concept {i}"},
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"results": {"bindings": bindings}})

    hits = await search("x", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_skips_non_aat_uris() -> None:
    """Ensure we don't return bindings whose URIs sit outside the AAT
    scheme (the SPARQL query already filters by skos:inScheme aat: but
    this is defensive belt-and-braces)."""
    bindings = [
        {
            "uri": {"type": "uri", "value": "http://vocab.getty.edu/ulan/500123"},
            "label": {"type": "literal", "value": "not-an-AAT entry"},
        },
        _oil_paint_binding(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": {"bindings": bindings}})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].aat_id == "300015050"


@pytest.mark.asyncio
async def test_search_skips_malformed_bindings() -> None:
    bindings = [
        {"uri": {"type": "uri", "value": "http://vocab.getty.edu/aat/NOT_A_NUMBER"}},  # aat_id not digits
        {"label": {"type": "literal", "value": "only a label"}},                       # no uri
        {"uri": {"type": "uri", "value": "http://vocab.getty.edu/aat/300015050"}},     # no label
        _oil_paint_binding(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": {"bindings": bindings}})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].aat_id == "300015050"


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []
