from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.password import hash_password
from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import Base, get_async_session
from app.main import app, embed_app
from app.middleware.rate_limiter import limiter
from app.models import Role, User, UserRole  # noqa: F401 — required for metadata
from app.models.role import Role as _Role
from app.models.user import User as _User

# Plugin routers are loaded dynamically at runtime via plugin_loader.load_active(),
# which uses AsyncSessionLocal (real Postgres).  In tests, Postgres is replaced with
# in-memory SQLite, so plugin_loader never runs and no plugin router is mounted.
# Register each native plugin router here directly so their endpoints are reachable,
# and import their models so Base.metadata.create_all() includes the plugin tables.
from app.plugins._native.collections.router import router as _collections_router
from app.plugins._native.named_entities import models as _ne_models  # noqa: F401 — register tables
from app.plugins._native.named_entities.router import router as _named_entities_router
app.include_router(_collections_router, prefix="/api/v1")
app.include_router(_named_entities_router, prefix="/api/v1")


# slowapi 0.1.9 has no built-in "enabled" flag.
# _check_request_limit is synchronous in this version; after it returns,
# slowapi reads request.state.view_rate_limit to inject rate-limit headers.
# The no-op must set that attribute to None so the subsequent _inject_headers
# call doesn't raise AttributeError.
def _no_rate_limit(request: object, *args: object, **kwargs: object) -> None:
    if hasattr(request, "state"):
        request.state.view_rate_limit = None

limiter._check_request_limit = _no_rate_limit  # type: ignore[method-assign]

TEST_USER_USERNAME = "testuser"
TEST_USER_PASSWORD = "testpassword1"
ADMIN_USERNAME = "admin_test"
ADMIN_PASSWORD = "adminpass1"
DESIGNER_USERNAME = "designer_test"
DESIGNER_PASSWORD = "designerpass1"
EIC_USERNAME = "eic_test"
EIC_PASSWORD = "eicpass1"

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
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


@pytest_asyncio.fixture(autouse=True)
async def clean_db(test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Truncate all tables before every test.

    The test_engine is session-scoped and uses StaticPool, so commits made by
    route handlers inside one test persist to subsequent tests.  This fixture
    deletes all rows (in reverse FK order) before each test starts, giving
    every test a clean, empty database.
    """
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(delete(table))
    yield


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_session
    embed_app.dependency_overrides[get_async_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
    app.dependency_overrides.clear()
    embed_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession) -> list[str]:
    roles = ["Admin", "EditorInChief", "Designer", "Editor", "User"]
    for name in roles:
        db_session.add(Role(name=name, description=f"{name} role"))
    await db_session.flush()
    return roles


@pytest_asyncio.fixture
async def seeded_admin(db_session: AsyncSession, seeded_roles: list[str]) -> _User:
    user = _User(
        username=ADMIN_USERNAME,
        email="admin_test@example.com",
        password_hash=hash_password(ADMIN_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    admin_role = await db_session.scalar(
        select(_Role).where(_Role.name == "Admin")
    )
    assert admin_role is not None
    db_session.add(UserRole(user_id=user.id, role_id=admin_role.id))
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def seeded_user(db_session: AsyncSession, seeded_roles: list[str]) -> _User:
    user = _User(
        username=TEST_USER_USERNAME,
        email="testuser@example.com",
        password_hash=hash_password(TEST_USER_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    editor_role = await db_session.scalar(
        select(_Role).where(_Role.name == "Editor")
    )
    assert editor_role is not None
    db_session.add(UserRole(user_id=user.id, role_id=editor_role.id))
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def seeded_designer(db_session: AsyncSession, seeded_roles: list[str]) -> _User:
    user = _User(
        username=DESIGNER_USERNAME,
        email="designer_test@example.com",
        password_hash=hash_password(DESIGNER_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    role = await db_session.scalar(select(_Role).where(_Role.name == "Designer"))
    assert role is not None
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def seeded_editorinchief(
    db_session: AsyncSession, seeded_roles: list[str]
) -> _User:
    user = _User(
        username=EIC_USERNAME,
        email="eic_test@example.com",
        password_hash=hash_password(EIC_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    role = await db_session.scalar(
        select(_Role).where(_Role.name == "EditorInChief")
    )
    assert role is not None
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.flush()
    return user


@pytest.fixture
def mock_existdb() -> AsyncMock:
    """Async mock of ExistDBClient for tests that touch eXist-db endpoints."""
    mock = AsyncMock(spec=ExistDBClient)
    mock.ping = AsyncMock(return_value=True)
    mock.ensure_root = AsyncMock(return_value=None)
    mock.collection_exists = AsyncMock(return_value=True)
    mock.create_collection = AsyncMock(return_value=None)
    mock.delete_collection = AsyncMock(return_value=None)
    mock.list_collection = AsyncMock(return_value=["doc1.xml"])
    mock.get_document = AsyncMock(return_value=b"<doc/>")
    mock.put_document = AsyncMock(return_value=None)
    mock.delete_document = AsyncMock(return_value=None)
    mock.xquery = AsyncMock(return_value=b"<results/>")
    return mock


@pytest_asyncio.fixture
async def client_with_existdb(
    db_session: AsyncSession, mock_existdb: AsyncMock
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client that overrides both the DB session and the ExistDB client."""

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_session
    app.dependency_overrides[get_existdb] = lambda: mock_existdb
    embed_app.dependency_overrides[get_async_session] = override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
    app.dependency_overrides.clear()
    embed_app.dependency_overrides.clear()
