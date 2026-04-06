import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.password import hash_password
from app.db.postgres import Base, get_async_session
from app.main import app
from app.middleware.rate_limiter import limiter
from app.models import Role, User, UserRole  # noqa: F401 — required for metadata
from app.models.role import Role as _Role
from app.models.user import User as _User

# slowapi 0.1.9 has no built-in "enabled" flag.
# _check_request_limit is synchronous in this version; after it returns,
# slowapi reads request.state.view_rate_limit to inject rate-limit headers.
# The no-op must set that attribute to None so the subsequent _inject_headers
# call doesn't raise AttributeError.
def _no_rate_limit(request: object, *args: object, **kwargs: object) -> None:
    if hasattr(request, "state"):
        request.state.view_rate_limit = None  # type: ignore[union-attr]

limiter._check_request_limit = _no_rate_limit

TEST_USER_USERNAME = "testuser"
TEST_USER_PASSWORD = "testpassword1"
ADMIN_USERNAME = "admin_test"
ADMIN_PASSWORD = "adminpass1"

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
    db_session.add(UserRole(user_id=user.id, role_id=editor_role.id))
    await db_session.flush()
    return user
