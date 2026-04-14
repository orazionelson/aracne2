"""Tests for the health check endpoint (GET /health).

PostgreSQL is the real in-memory SQLite.  eXist-db is mocked via the
client_with_existdb fixture so the test never opens a real TCP connection.
"""

import pytest
from httpx import AsyncClient

from app.models.user import User


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_healthy_when_both_services_are_ok(
    client_with_existdb: AsyncClient,
) -> None:
    """Health check returns 200 with status 'healthy' when all services respond."""
    res = await client_with_existdb.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["status"] == "healthy"
    assert body["services"]["postgres"]["status"] == "ok"
    assert body["services"]["existdb"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_degraded_when_existdb_is_down(
    client_with_existdb: AsyncClient,
    mock_existdb: object,
) -> None:
    """Health check returns 200 with status 'degraded' when eXist-db ping fails."""
    from unittest.mock import AsyncMock
    mock_existdb.ping = AsyncMock(return_value=False)  # type: ignore[union-attr]

    res = await client_with_existdb.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["status"] == "degraded"
    assert body["services"]["existdb"]["status"] == "error"
    assert body["services"]["postgres"]["status"] == "ok"
