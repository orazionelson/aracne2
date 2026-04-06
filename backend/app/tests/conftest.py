import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.core.password import hash_password
from app.main import app
from app.db.postgres import Base, get_async_session
from app.middleware.rate_limiter import limiter

# Disable rate limiting for the entire test session — the in-memory counter
# accumulates across tests and causes 429s after 10 POST /auth/login calls.
limiter._enabled = False
from app.models import Role, User, UserRole  # noqa: F401 — required for metadata
from app.models.role import Role as _Role
from app.models.user import User as _User

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
