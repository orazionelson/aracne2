"""Trismegistos search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.trismegistos.service import search


def _person_row() -> dict[str, object]:
    return {
        "id": "12345",
        "type": "person",
        "name": "Apollonios son of Ptolemaios",
        "dates": "150 BC – 130 BC",
        "provenance": "Egypt, Herakleopolites",
    }


def _place_row() -> dict[str, object]:
    return {
        "id": "8423",
        "type": "place",
        "name": "Oxyrhynchos",
        "provenance": "Egypt, Oxyrhynchites",
    }


def _text_row() -> dict[str, object]:
    return {
        "id": "77231",
        "type": "text",
        "name": "P.Oxy. I 1",
        "dates": "200–300 AD",
        "language": "Greek",
        "genre": "literary",
    }


# ── Empty key short-circuits ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_empty_api_key_returns_empty_list_no_call() -> None:
    """With an empty key the service must not hit the network at all —
    the router will surface a 503 to the caller."""
    called = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"results": [_person_row()]})

    hits = await search(
        "x", api_key="", transport=httpx.MockTransport(handler),
    )
    assert hits == []
    assert called["n"] == 0


# ── Parsing ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_parses_person_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"results": [_person_row()]})

    hits = await search(
        "apollonios", api_key="SECRET_KEY",
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 1
    hit = hits[0]
    assert hit.tm_id == "12345"
    assert hit.uri == "https://www.trismegistos.org/person/12345"
    assert hit.label == "Apollonios son of Ptolemaios"
    assert hit.kind == "person"
    assert "150 BC" in hit.detail
    assert "Herakleopolites" in hit.detail
    # API key goes into the bearer header.
    assert captured["auth"] == "Bearer SECRET_KEY"
    assert "trismegistos.org/api/v3/search" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_parses_place_and_text() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"results": [_place_row(), _text_row()]},
        )

    hits = await search(
        "x", api_key="KEY", transport=httpx.MockTransport(handler),
    )
    kinds = {h.kind for h in hits}
    assert kinds == {"place", "text"}
    assert any(h.uri == "https://www.trismegistos.org/place/8423" for h in hits)
    assert any(h.uri == "https://www.trismegistos.org/text/77231" for h in hits)


@pytest.mark.asyncio
async def test_search_classifies_via_url_hint_when_type_missing() -> None:
    row = {
        "id": "9999",
        "name": "Record without explicit type",
        "url": "https://www.trismegistos.org/text/9999",
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [row]})

    hits = await search("x", api_key="KEY", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "text"


@pytest.mark.asyncio
async def test_search_accepts_envelope_variants() -> None:
    """TM has used multiple envelope shapes — results / hits / items /
    data / data.hits. Cover the most common ones."""
    for envelope in (
        {"results": [_person_row()]},
        {"hits": [_person_row()]},
        {"items": [_person_row()]},
        {"data": [_person_row()]},
        {"data": {"hits": [_person_row()]}},
    ):
        def handler(_: httpx.Request, payload: object = envelope) -> httpx.Response:
            return httpx.Response(200, json=payload)

        hits = await search(
            "x", api_key="KEY", transport=httpx.MockTransport(handler),
        )
        assert len(hits) == 1, f"Envelope failed: {envelope}"


@pytest.mark.asyncio
async def test_search_skips_rows_without_id_or_name() -> None:
    rows = [
        {"type": "person", "name": "No id"},
        {"id": "1", "type": "person"},  # no name
        {"id": "abc", "type": "person", "name": "Non-numeric id"},
        _person_row(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": rows})

    hits = await search("x", api_key="KEY", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].tm_id == "12345"


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {"id": str(1000 + i), "type": "person", "name": f"Person {i}"}
            for i in range(20)
        ]
        return httpx.Response(200, json={"results": items})

    hits = await search(
        "x", api_key="KEY", rows=5,
        transport=httpx.MockTransport(handler),
    )
    assert len(hits) == 5


# ── Fail-soft ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_unauthorized_returns_empty() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    hits = await search("x", api_key="BAD", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search("x", api_key="KEY", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hits = await search("x", api_key="KEY", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hits = await search("x", api_key="KEY", transport=httpx.MockTransport(handler))
    assert hits == []
