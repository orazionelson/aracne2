"""GND search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.gnd.service import search

_GND_TYPE_URI = "https://d-nb.info/standards/elementset/gnd#"


def _goethe_hit() -> dict[str, object]:
    return {
        "id": "https://d-nb.info/gnd/118524534",
        "gndIdentifier": "118524534",
        "preferredName": "Goethe, Johann Wolfgang von",
        "type": [
            f"{_GND_TYPE_URI}DifferentiatedPerson",
            f"{_GND_TYPE_URI}Person",
            f"{_GND_TYPE_URI}AuthorityResource",
        ],
        "dateOfBirth": ["1749"],
        "dateOfDeath": ["1832"],
        "professionOrOccupation": [
            {"label": "Schriftsteller"},
            {"label": "Dichter"},
        ],
    }


def _frankfurt_hit() -> dict[str, object]:
    return {
        "id": "https://d-nb.info/gnd/4018102-7",
        "gndIdentifier": "4018102-7",
        "preferredName": "Frankfurt am Main",
        "type": [
            f"{_GND_TYPE_URI}PlaceOrGeographicName",
            f"{_GND_TYPE_URI}AuthorityResource",
        ],
    }


def _dnb_corporate_hit() -> dict[str, object]:
    return {
        "id": "https://d-nb.info/gnd/1001465-9",
        "gndIdentifier": "1001465-9",
        "preferredName": "Deutsche Nationalbibliothek",
        "type": [
            f"{_GND_TYPE_URI}CorporateBody",
            f"{_GND_TYPE_URI}AuthorityResource",
        ],
    }


@pytest.mark.asyncio
async def test_search_parses_person_hit() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"member": [_goethe_hit()], "totalItems": 1})

    hits = await search("goethe", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.gnd_id == "118524534"
    assert hit.uri == "https://d-nb.info/gnd/118524534"
    assert hit.label == "Goethe, Johann Wolfgang von"
    assert hit.kind == "person"
    # Detail pulls dates + first two professions.
    assert "1749" in hit.detail
    assert "1832" in hit.detail
    assert "Schriftsteller" in hit.detail
    # Request hit the search endpoint with the right params.
    assert "lobid.org/gnd/search" in str(captured["url"])
    assert "q=goethe" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_classifies_place() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"member": [_frankfurt_hit()]})

    hits = await search("frankfurt", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "place"


@pytest.mark.asyncio
async def test_search_classifies_corporate() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"member": [_dnb_corporate_hit()]})

    hits = await search("dnb", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "corporate"


@pytest.mark.asyncio
async def test_search_caps_rows() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        items = [
            {
                "id": f"https://d-nb.info/gnd/100000{i}",
                "gndIdentifier": f"100000{i}",
                "preferredName": f"Person {i}",
                "type": [f"{_GND_TYPE_URI}Person"],
            }
            for i in range(20)
        ]
        return httpx.Response(200, json={"member": items})

    hits = await search("x", rows=5, transport=httpx.MockTransport(handler))
    assert len(hits) == 5


@pytest.mark.asyncio
async def test_search_rows_clamped() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"member": [_goethe_hit()]})

    hits = await search("g", rows=0, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hits = await search("g", rows=999, transport=httpx.MockTransport(handler))
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_search_skips_items_without_required_fields() -> None:
    broken = [
        {"id": "https://d-nb.info/gnd/nogenuid", "preferredName": "No id"},  # no gndIdentifier
        {
            "id": "https://example.com/not-gnd",  # wrong URI host
            "gndIdentifier": "42",
            "preferredName": "Wrong host",
            "type": [f"{_GND_TYPE_URI}Person"],
        },
        _goethe_hit(),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"member": broken})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    assert hits[0].gnd_id == "118524534"


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


@pytest.mark.asyncio
async def test_search_classifies_unknown_types_as_other() -> None:
    item = {
        "id": "https://d-nb.info/gnd/999999",
        "gndIdentifier": "999999",
        "preferredName": "Mystery entity",
        "type": [f"{_GND_TYPE_URI}SomethingExotic"],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"member": [item]})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].kind == "other"
