# PHASE 01e — Tests: conftest + scaffolding test suite
# Prerequisite: CLAUDE.md loaded. Phases 01b and 01c complete.
# Goal: `make test` passes with all tests green.
#
# Test strategy:
#   - Unit/integration tests use SQLite in-memory (fast, no Docker dependency)
#   - PostgreSQL-specific tests (triggers, INET type, JSONB) are tagged @pytest.mark.pg
#     and run in CI against a real PostgreSQL container
#   - eXist-db is mocked via dependency override in all scaffolding tests

Implement everything below. Every file must be complete and working.

---

## File: backend/app/tests/conftest.py

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.postgres import Base, get_async_session
from app.models import Role, User, UserRole  # noqa: F401 — required for metadata

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_session():
        yield db_session
    app.dependency_overrides[get_async_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession) -> list[str]:
    roles = ["Admin", "EditorInChief", "Designer", "Editor", "User"]
    for name in roles:
        db_session.add(Role(name=name, description=f"{name} role"))
    await db_session.flush()
    return roles
```

---

## File: backend/app/tests/test_scaffolding.py

```python
import pytest
import uuid
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

async def test_orm_user_insert_does_not_raise(
    db_session, seeded_roles
) -> None:
    """
    Verifies that the ORM model is correctly mapped and a user can be inserted.
    NOTE: this test runs against SQLite in-memory.
    The PostgreSQL trigger fn_assign_default_role does NOT run in SQLite.
    The trigger is tested separately in tests/integration/test_pg_triggers.py
    which runs against a real PostgreSQL container in CI.
    """
    import passlib.hash as ph
    from app.models import User, UserRole
    from sqlalchemy import select

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
```
