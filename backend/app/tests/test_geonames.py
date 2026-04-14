"""Tests for the GeoNames search proxy (GET /geonames/search).

The endpoint proxies an external GeoNames API call.  Tests patch httpx.AsyncClient
so no real network connection is made.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import User
from app.tests.conftest import TEST_USER_PASSWORD, TEST_USER_USERNAME


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login_as(client: AsyncClient, username: str, password: str) -> str:
    res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": username, "password": password},
    )
    assert res.status_code == 200
    return str(res.json()["data"]["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mock_geonames_response(places: list[dict]) -> MagicMock:
    """Build a mock httpx response that returns the given geonames results."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"geonames": places}
    return mock_resp


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_geonames_search_returns_places_for_authenticated_user(
    client: AsyncClient, seeded_user: User
) -> None:
    """Authenticated user receives a list of GeonamesPlace items."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        return_value=_mock_geonames_response([
            {
                "name": "Rome",
                "adminName1": "Lazio",
                "countryName": "Italy",
                "geonameId": 3169070,
            },
            {
                "name": "Roma",
                "adminName1": "Texas",
                "countryName": "United States",
                "geonameId": 4726491,
            },
        ])
    )

    with patch("app.routers.geonames.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/geonames/search?q=Rome",
            headers=_auth(token),
        )

    assert res.status_code == 200
    data = res.json()["data"]
    assert len(data) == 2
    assert data[0]["name"] == "Rome"
    assert data[0]["country"] == "Italy"
    assert data[0]["geonames_id"] == 3169070


@pytest.mark.asyncio
async def test_geonames_search_unauthenticated_returns_401(
    client: AsyncClient,
) -> None:
    """Unauthenticated request is rejected with 401."""
    res = await client.get("/api/v1/geonames/search?q=Rome")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_geonames_search_query_too_short_returns_422(
    client: AsyncClient, seeded_user: User
) -> None:
    """Query shorter than 2 characters is rejected with 422."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/geonames/search?q=R",
        headers=_auth(token),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_geonames_search_returns_empty_list_on_upstream_error(
    client: AsyncClient, seeded_user: User
) -> None:
    """When the upstream GeoNames call fails, the endpoint degrades gracefully to []."""
    import httpx as _httpx

    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        side_effect=_httpx.RequestError("connection refused", request=MagicMock())
    )

    with patch("app.routers.geonames.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/geonames/search?q=Rome",
            headers=_auth(token),
        )

    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_geonames_search_returns_empty_list_on_http_error(
    client: AsyncClient, seeded_user: User
) -> None:
    """When the upstream server returns a non-2xx status, the endpoint returns []."""
    import httpx as _httpx

    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    error_response = MagicMock()
    error_response.status_code = 503

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "503", request=MagicMock(), response=error_response
        )
        return mock_resp

    mock_client.get = _raise

    with patch("app.routers.geonames.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/geonames/search?q=Rome",
            headers=_auth(token),
        )

    assert res.status_code == 200
    assert res.json()["data"] == []
