"""Tests for the Wikidata search proxy (GET /wikidata/search).

The endpoint proxies an external Wikidata API call. Tests patch
httpx.AsyncClient so no real network connection is made in CI.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.tests.conftest import TEST_USER_PASSWORD, TEST_USER_USERNAME


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mock_wikidata_response(hits: list[dict[str, Any]]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"search": hits, "success": 1}
    return mock_resp


_DANTE_HIT: dict[str, Any] = {
    "id": "Q1067",
    "title": "Q1067",
    "label": "Dante Alighieri",
    "description": "Italian poet, writer, and philosopher (c.1265–1321)",
    "concepturi": "http://www.wikidata.org/entity/Q1067",
    "url": "//www.wikidata.org/wiki/Q1067",
}


@pytest.mark.asyncio
async def test_search_returns_structured_hits_for_authenticated_user(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=_mock_wikidata_response([_DANTE_HIT]))

    with patch("app.routers.wikidata.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/wikidata/search?q=dante",
            headers=_auth(token),
        )

    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 1
    assert data[0]["qid"] == "Q1067"
    assert data[0]["label"] == "Dante Alighieri"
    assert data[0]["uri"] == "http://www.wikidata.org/entity/Q1067"
    assert "philosopher" in (data[0]["description"] or "")


@pytest.mark.asyncio
async def test_search_unauthenticated_returns_401(client: AsyncClient) -> None:
    res = await client.get("/api/v1/wikidata/search?q=dante")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_search_query_too_short_returns_422(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/wikidata/search?q=d",
        headers=_auth(token),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_search_invalid_lang_returns_422(
    client: AsyncClient, seeded_user: User
) -> None:
    """Upstream Wikidata rejects arbitrary garbage; we validate the shape
    at the router level to avoid wasting an upstream round-trip."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/wikidata/search?q=dante&lang=ZZZ1",
        headers=_auth(token),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_search_degrades_to_empty_list_on_request_error(
    client: AsyncClient, seeded_user: User
) -> None:
    import httpx as _httpx

    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        side_effect=_httpx.RequestError("connection refused", request=MagicMock())
    )

    with patch("app.routers.wikidata.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/wikidata/search?q=dante",
            headers=_auth(token),
        )

    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_search_skips_hits_missing_required_fields(
    client: AsyncClient, seeded_user: User
) -> None:
    """Wikidata occasionally returns hits with a label but no concepturi.
    The proxy drops those rather than emitting fragile half-records."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    broken_hit: dict[str, Any] = {
        "id": "Q999999",
        "label": "Broken entity",
        "description": "Missing concepturi on purpose",
        # no "concepturi"
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        return_value=_mock_wikidata_response([_DANTE_HIT, broken_hit])
    )

    with patch("app.routers.wikidata.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/wikidata/search?q=dante",
            headers=_auth(token),
        )

    assert res.status_code == 200
    data = res.json()["data"]
    assert [row["qid"] for row in data] == ["Q1067"]


@pytest.mark.asyncio
async def test_search_passes_lang_and_limit_to_upstream(
    client: AsyncClient, seeded_user: User
) -> None:
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=_mock_wikidata_response([]))

    with patch("app.routers.wikidata.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/wikidata/search?q=firenze&lang=en&limit=5",
            headers=_auth(token),
        )

    assert res.status_code == 200
    # Verify the forwarded params were set correctly — the UI relies on
    # lang switching for multilingual corpora.
    call_kwargs = mock_client.get.call_args.kwargs
    params = call_kwargs["params"]
    assert params["search"] == "firenze"
    assert params["language"] == "en"
    assert params["limit"] == "5"
    assert params["type"] == "item"
