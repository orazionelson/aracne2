"""Tests for the VIAF autosuggest proxy (GET /viaf/autosuggest).

The endpoint proxies an external VIAF API call.  Tests patch httpx.AsyncClient
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


def _mock_viaf_response(names: list[str]) -> MagicMock:
    """Build a mock httpx response that returns the given displayForm names."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": [{"displayForm": name} for name in names]
    }
    return mock_resp


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viaf_autosuggest_returns_names_for_authenticated_user(
    client: AsyncClient, seeded_user: User
) -> None:
    """Authenticated user receives a list of displayForm strings from VIAF."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=_mock_viaf_response(["Dante Alighieri", "Dante Gabriel Rossetti"]))

    with patch("app.routers.viaf.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/viaf/autosuggest?query=dante",
            headers=_auth(token),
        )

    assert res.status_code == 200
    data = res.json()["data"]
    assert "Dante Alighieri" in data
    assert len(data) == 2


@pytest.mark.asyncio
async def test_viaf_autosuggest_unauthenticated_returns_401(
    client: AsyncClient,
) -> None:
    """Unauthenticated request is rejected with 401."""
    res = await client.get("/api/v1/viaf/autosuggest?query=dante")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_viaf_autosuggest_query_too_short_returns_422(
    client: AsyncClient, seeded_user: User
) -> None:
    """Query shorter than 2 characters is rejected with 422."""
    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)
    res = await client.get(
        "/api/v1/viaf/autosuggest?query=d",
        headers=_auth(token),
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_viaf_autosuggest_returns_empty_list_on_upstream_error(
    client: AsyncClient, seeded_user: User
) -> None:
    """When the upstream VIAF call fails, the endpoint degrades gracefully to []."""
    import httpx as _httpx

    token = await _login_as(client, TEST_USER_USERNAME, TEST_USER_PASSWORD)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(
        side_effect=_httpx.RequestError("connection refused", request=MagicMock())
    )

    with patch("app.routers.viaf.httpx.AsyncClient", return_value=mock_client):
        res = await client.get(
            "/api/v1/viaf/autosuggest?query=dante",
            headers=_auth(token),
        )

    assert res.status_code == 200
    assert res.json()["data"] == []
