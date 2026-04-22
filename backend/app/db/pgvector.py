"""pgvector — optional vector store for RAG.

The pgvector service is a separate Postgres instance, enabled via the
``ai-local`` Compose profile. The backend connects lazily: if
``PGVECTOR_HOST`` is not set or the service is unreachable, everything RAG
falls back to no-op with a warning log.

Keeping this isolated from the main platform DB means:
- no schema changes to the core data model when RAG iterates;
- vector-only workloads (heavy sequential scans during ingest, ANN queries)
  do not contend with editorial traffic;
- we can drop and rebuild the vector index without touching user data.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class PgvectorBase(DeclarativeBase):
    """Separate declarative base so the main postgres Base.metadata does not
    include vector tables (keeps the two schemas strictly disjoint)."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _init_engine() -> None:
    """Create the engine once on first use. Idempotent."""
    global _engine, _session_factory
    if _engine is not None:
        return
    url = settings.pgvector_url
    if url is None:
        return
    _engine = create_async_engine(
        url,
        echo=settings.is_development,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def is_available() -> bool:
    """True when PGVECTOR_HOST is configured. Does not verify connectivity —
    the first query will fail gracefully if the service is unreachable."""
    return settings.pgvector_url is not None


def get_engine() -> AsyncEngine | None:
    _init_engine()
    return _engine


async def get_pgvector_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a pgvector session. Raises RuntimeError if
    pgvector is not configured — callers should gate on ``is_available()``
    before reaching the endpoint that consumes this dependency."""
    _init_engine()
    if _session_factory is None:
        raise RuntimeError("pgvector is not configured (PGVECTOR_HOST is empty)")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    """Return the pgvector session factory (or None if pgvector is not
    configured). Callers use this to open ad-hoc sessions outside the
    FastAPI dependency flow, e.g. inside the AI service layer."""
    _init_engine()
    return _session_factory


async def ensure_schema() -> None:
    """Create the ``vector`` extension and the RAG tables if they are missing.

    Called from the FastAPI lifespan. Non-fatal: failures are logged and the
    backend continues to start (RAG becomes unavailable, rest of the app
    keeps working).
    """
    import structlog
    from sqlalchemy import text

    logger = structlog.get_logger()
    _init_engine()
    if _engine is None:
        logger.info("pgvector_skipped_not_configured")
        return

    # Import models so PgvectorBase.metadata knows about them before create_all.
    from app.models.ai_context_chunk import AiContextChunk  # noqa: F401

    async with _engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(PgvectorBase.metadata.create_all)
    logger.info("pgvector_ready")
