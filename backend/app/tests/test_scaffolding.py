import uuid

import pytest
from httpx import AsyncClient


async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert body["data"]["status"] in ["healthy", "degraded"]
    assert "services" in body["data"]
    assert "postgres" in body["data"]["services"]
    assert "existdb" in body["data"]["services"]


async def test_health_response_has_version(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.json()["data"]["version"] == "1.0.0"


async def test_unknown_route_returns_404_in_error_format(client: AsyncClient) -> None:
    r = await client.get("/api/v1/this-does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]


async def test_request_id_header_present(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert "x-request-id" in r.headers
    # Verify the value is a valid UUID
    uuid.UUID(r.headers["x-request-id"])


async def test_settings_jwt_secret_too_short() -> None:
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises((ValidationError, ValueError)):
        Settings(
            postgres_host="localhost",
            postgres_db="x",
            postgres_user="x",
            postgres_password="x",
            existdb_url="http://x",
            existdb_user="x",
            existdb_password="x",
            jwt_secret="tooshort",  # less than 64 characters
        )


async def test_orm_user_insert_does_not_raise(db_session, seeded_roles) -> None:
    """
    Verifies that the ORM model is correctly mapped and a user can be inserted.
    NOTE: this test runs against SQLite in-memory.
    The PostgreSQL trigger fn_assign_default_role does NOT run in SQLite.
    The trigger is tested separately in tests/integration/test_pg_triggers.py
    which runs against a real PostgreSQL container in CI.
    """
    import passlib.hash as ph
    from sqlalchemy import select

    from app.models import User, UserRole

    user = User(
        id=uuid.uuid4(),
        username="testuser_scaffold",
        email="scaffold@test.com",
        password_hash=ph.bcrypt.hash("Password1!"),
    )
    db_session.add(user)
    await db_session.flush()

    result = await db_session.execute(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    roles_assigned = result.scalars().all()
    # SQLite: empty list (trigger inactive); PostgreSQL CI: list with 1 element
    assert isinstance(roles_assigned, list)
