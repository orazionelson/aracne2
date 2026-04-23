"""ORCID search service — no network, httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.plugins.orcid.service import search


@pytest.mark.asyncio
async def test_search_parses_expanded_hits() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(
            200,
            json={
                "num-found": 1,
                "expanded-result": [
                    {
                        "orcid-id": "0000-0002-1825-0097",
                        "given-names": "Jane",
                        "family-names": "Doe",
                        "credit-name": "J. Doe",
                        "institution-name": ["University of X", "Institute of Y", "University of X"],
                    }
                ],
            },
        )

    hits = await search("jane doe", rows=10, transport=httpx.MockTransport(handler))
    assert len(hits) == 1
    hit = hits[0]
    assert hit.orcid == "0000-0002-1825-0097"
    assert hit.uri == "https://orcid.org/0000-0002-1825-0097"
    assert hit.given_names == "Jane"
    assert hit.family_name == "Doe"
    assert hit.credit_name == "J. Doe"
    # Institutions are deduplicated while preserving order.
    assert hit.affiliations == ["University of X", "Institute of Y"]
    # The label prefers the credit-name when set.
    assert hit.label == "J. Doe"
    # Request went to the expanded-search endpoint with rows=10.
    assert "expanded-search" in str(captured["url"])
    assert "rows=10" in str(captured["url"])


@pytest.mark.asyncio
async def test_search_label_fallbacks_to_given_family() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "expanded-result": [
                    {
                        "orcid-id": "0000-0002-0000-0001",
                        "given-names": "A",
                        "family-names": "B",
                    }
                ]
            },
        )

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].label == "A B"


@pytest.mark.asyncio
async def test_search_label_falls_back_to_orcid_when_no_names() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"expanded-result": [{"orcid-id": "0000-0000-0000-0001"}]}
        )

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits[0].label == "0000-0000-0000-0001"


@pytest.mark.asyncio
async def test_search_rows_is_clamped_to_sensible_range() -> None:
    """Passing ``rows=500`` must not leak to the upstream — we clamp it
    to 25 client-side so the editor UX stays sane."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"expanded-result": []})

    await search("x", rows=500, transport=httpx.MockTransport(handler))
    assert "rows=25" in captured["url"]


@pytest.mark.asyncio
async def test_search_degrades_to_empty_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_degrades_to_empty_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []


@pytest.mark.asyncio
async def test_search_skips_rows_without_orcid_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "expanded-result": [
                    {"given-names": "NoOrcid"},
                    {"orcid-id": "0000-0002-0000-0002", "given-names": "Valid"},
                    {"orcid-id": ""},  # empty id
                ]
            },
        )

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert [h.orcid for h in hits] == ["0000-0002-0000-0002"]


@pytest.mark.asyncio
async def test_search_tolerates_missing_expanded_result() -> None:
    """Upstream sometimes returns ``{"num-found": 0}`` with no list."""
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"num-found": 0})

    hits = await search("x", transport=httpx.MockTransport(handler))
    assert hits == []
