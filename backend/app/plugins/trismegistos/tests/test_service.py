"""Trismegistos ID-resolver — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.trismegistos.service import resolve


# ── Shared fixtures ────────────────────────────────────────────────────────


def _text_relations_payload() -> list[dict[str, object]]:
    """Abbreviated but realistic shape returned by
    ``/dataservices/texrelations/<id>``. Only non-null partners are
    kept; the rest are ``null`` as in the real response."""
    return [
        {"TM_ID": ["9"]},
        {"EDB": None},
        {"HGV": ["9a", "9b"]},
        {"DDBDP": ["9"]},
        {"BL_online": ["9a", "9b"]},
    ]


def _geo_relations_payload() -> list[dict[str, object]]:
    """Realistic ``/dataservices/georelations/<id>`` shape, loosely
    modelled on the Alexandria response."""
    return [
        {"TM_Geo_ID": None},
        {"Syriaca": ["572"]},
        {"DASI": None},
        {"Wikipedia": ["Alexandria"]},
    ]


# ── Person resolver: no network, validates numeric ID ──────────────────────


@pytest.mark.asyncio
async def test_resolve_person_composes_canonical_url_without_network() -> None:
    """Persons have no JSON endpoint — resolver must not touch the
    network and must return a hit with the composed URL."""
    called = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(500)

    hit = await resolve(
        kind="person",
        identifier="12345",
        transport=httpx.MockTransport(handler),
    )
    assert called["n"] == 0
    assert hit is not None
    assert hit.tm_id == "12345"
    assert hit.uri == "https://www.trismegistos.org/person/12345"
    assert hit.kind == "person"
    assert hit.partners == {}
    assert "12345" in hit.label


@pytest.mark.asyncio
async def test_resolve_person_rejects_non_numeric_id() -> None:
    hit = await resolve(kind="person", identifier="pap.1234")
    assert hit is None


# ── Place resolver: georelations JSON ──────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_place_parses_partners_and_derives_wikipedia_label() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_geo_relations_payload())

    hit = await resolve(
        kind="place",
        identifier="100",
        transport=httpx.MockTransport(handler),
    )
    assert hit is not None
    assert hit.tm_id == "100"
    assert hit.uri == "https://www.trismegistos.org/place/100"
    assert hit.kind == "place"
    assert hit.partners["Wikipedia"] == ["Alexandria"]
    assert hit.partners["Syriaca"] == ["572"]
    # Wikipedia slug becomes the label.
    assert hit.label == "Alexandria"
    # Called georelations, not texrelations.
    assert "dataservices/georelations/100" in captured["url"]


@pytest.mark.asyncio
async def test_resolve_place_soft_404_returns_none() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Message": "This GEO ID is not in our database."},
        )

    hit = await resolve(
        kind="place",
        identifier="999999",
        transport=httpx.MockTransport(handler),
    )
    assert hit is None


@pytest.mark.asyncio
async def test_resolve_place_rejects_non_numeric_id() -> None:
    """Places are identified by TM numeric Geo IDs — reject anything
    else without touching the network."""
    called = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json=_geo_relations_payload())

    hit = await resolve(
        kind="place",
        identifier="oxyrhynchos",
        transport=httpx.MockTransport(handler),
    )
    assert hit is None
    assert called["n"] == 0


# ── Text resolver: texrelations JSON with / without ?source= ──────────────


@pytest.mark.asyncio
async def test_resolve_text_direct_tm_id_uses_no_source_param() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_text_relations_payload())

    hit = await resolve(
        kind="text",
        identifier="9",
        source="trismegistos",
        transport=httpx.MockTransport(handler),
    )
    assert hit is not None
    assert hit.tm_id == "9"
    assert hit.uri == "https://www.trismegistos.org/text/9"
    assert hit.partners == {
        "HGV": ["9a", "9b"],
        "DDBDP": ["9"],
        "BL_online": ["9a", "9b"],
    }
    # HGV partner wins the label race ("HGV 9a").
    assert hit.label == "HGV 9a"
    # Trismegistos source means no ?source= param.
    assert "dataservices/texrelations/9" in captured["url"]
    assert "source=" not in captured["url"]


@pytest.mark.asyncio
async def test_resolve_text_reverse_lookup_passes_source_and_resolves_tm_id() -> None:
    """Paste ``9a`` with source=hgv → upstream resolves it to TM id 9."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_text_relations_payload())

    hit = await resolve(
        kind="text",
        identifier="9a",
        source="hgv",
        transport=httpx.MockTransport(handler),
    )
    assert hit is not None
    # Response-side TM_ID (9) wins over the input (9a).
    assert hit.tm_id == "9"
    assert hit.uri == "https://www.trismegistos.org/text/9"
    assert "source=hgv" in captured["url"]


@pytest.mark.asyncio
async def test_resolve_text_soft_404_returns_none() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Message": "This ID is not in our database."},
        )

    hit = await resolve(
        kind="text",
        identifier="xxx",
        source="ddbdp",
        transport=httpx.MockTransport(handler),
    )
    assert hit is None


@pytest.mark.asyncio
async def test_resolve_text_invalid_chars_short_circuit() -> None:
    """Spaces, angle brackets, quotes — reject without a network call
    so no crafted input ever reaches the URL."""
    called = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json=_text_relations_payload())

    for bad in ["9 OR 1=1", "<script>", "a'b", "pap?foo"]:
        hit = await resolve(
            kind="text",
            identifier=bad,
            transport=httpx.MockTransport(handler),
        )
        assert hit is None
    assert called["n"] == 0


# ── Fail-soft ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_fail_soft_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hit = await resolve(
        kind="text", identifier="9",
        transport=httpx.MockTransport(handler),
    )
    assert hit is None


@pytest.mark.asyncio
async def test_resolve_fail_soft_on_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    hit = await resolve(
        kind="place", identifier="100",
        transport=httpx.MockTransport(handler),
    )
    assert hit is None


@pytest.mark.asyncio
async def test_resolve_fail_soft_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    hit = await resolve(
        kind="text", identifier="9",
        transport=httpx.MockTransport(handler),
    )
    assert hit is None
