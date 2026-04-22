"""RAG retrieval — given a query, return the most relevant indexed chunks.

Retrieval only. Indexing (bulk writes of embeddings for the TEI P5
Guidelines, collection schemas, …) is handled by separate scripts in
``backend/scripts/``; at runtime the RAG service is read-only.

Fail-soft: any problem (pgvector not configured, Ollama unreachable, empty
index) results in an empty retrieval, NOT a 500 to the user. RAG augments
prompts when it can; when it cannot, the base prompt still runs.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.pgvector import is_available
from app.models.ai_context_chunk import AiContextChunk
from app.models.system_setting import SystemSetting
from app.plugins._native.ai.embeddings import EmbeddingUnavailable, embed_text

logger = structlog.get_logger()

# Rough char-per-token heuristic used to enforce the token budget without
# pulling in a real tokenizer. Good enough for English / Italian mixed text.
_CHARS_PER_TOKEN = 4


@dataclass
class RetrievedChunk:
    text: str
    source_type: str
    source_id: str
    chunk_index: int
    score: float  # cosine similarity in [-1, 1]; higher is better


async def _read_int(db: AsyncSession, key: str, default: int) -> int:
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None or not row.value:
        return default
    try:
        return int(row.value)
    except ValueError:
        return default


async def _read_bool(db: AsyncSession, key: str, default: bool) -> bool:
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        return default
    return row.value.strip().lower() == "true"


async def is_enabled(platform_db: AsyncSession) -> bool:
    """True when the admin has flipped the master switch AND pgvector is
    configured. Callers use this as an early gate to skip retrieval work
    when RAG is off."""
    if not is_available():
        return False
    return await _read_bool(platform_db, "ai_rag_enabled", False)


async def retrieve(
    platform_db: AsyncSession,
    vector_db: AsyncSession,
    query: str,
    *,
    top_k: int | None = None,
    token_budget: int | None = None,
) -> list[RetrievedChunk]:
    """Embed *query* and return the top matching chunks under *token_budget*.

    ``platform_db`` is the main platform session (reads settings and the
    embedding model name); ``vector_db`` is the pgvector session where
    the chunks and their embeddings live. Both are required because the
    two live in separate databases.

    Returns an empty list on any failure. Logs the reason at WARNING level.
    """
    if not query.strip():
        return []
    if top_k is None:
        top_k = await _read_int(platform_db, "ai_rag_top_k", 5)
    if token_budget is None:
        token_budget = await _read_int(platform_db, "ai_rag_context_tokens", 1500)

    try:
        query_vec = await embed_text(platform_db, query)
    except EmbeddingUnavailable as exc:
        logger.warning("rag_embedding_unavailable", error=str(exc))
        return []

    # Cosine distance via pgvector's <=> operator; convert to similarity so
    # higher = better. ``embedding::vector`` lets asyncpg bind as a literal
    # array without pulling in the pgvector asyncpg codec.
    try:
        stmt = (
            select(
                AiContextChunk.text,
                AiContextChunk.source_type,
                AiContextChunk.source_id,
                AiContextChunk.chunk_index,
                (text("1 - (embedding <=> CAST(:qvec AS vector))")).label("score"),
            )
            .order_by(text("embedding <=> CAST(:qvec AS vector)"))
            .limit(top_k)
        )
        result = await vector_db.execute(stmt, {"qvec": _vec_literal(query_vec)})
        rows = result.all()
    except Exception as exc:  # noqa: BLE001 — any DB error degrades to empty
        logger.warning("rag_retrieval_failed", error=str(exc))
        return []

    # Enforce the token budget by truncating the *list* of chunks; we do
    # not cut individual chunks because mid-chunk truncation is noisy on
    # XML / structured text.
    out: list[RetrievedChunk] = []
    used_chars = 0
    char_budget = token_budget * _CHARS_PER_TOKEN
    for row in rows:
        chunk_text = row.text  # type: ignore[attr-defined]
        if used_chars + len(chunk_text) > char_budget and out:
            break
        out.append(
            RetrievedChunk(
                text=chunk_text,
                source_type=row.source_type,  # type: ignore[attr-defined]
                source_id=row.source_id,  # type: ignore[attr-defined]
                chunk_index=row.chunk_index,  # type: ignore[attr-defined]
                score=float(row.score),  # type: ignore[attr-defined]
            )
        )
        used_chars += len(chunk_text)
    return out


def format_chunks(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a plain text block suitable for prompt
    injection. Each chunk is separated by a horizontal rule and prefixed
    with its source identifier for lightweight traceability in logs."""
    if not chunks:
        return ""
    parts: list[str] = []
    for c in chunks:
        parts.append(f"--- {c.source_type}:{c.source_id}#{c.chunk_index} ---\n{c.text.strip()}")
    return "\n\n".join(parts)


def _vec_literal(vec: list[float]) -> str:
    """Format a Python list as the pgvector literal ``[0.1,0.2,…]``.

    Kept as a string to sidestep the pgvector asyncpg codec registration
    dance — the CAST in the SQL handles the type conversion at the server.
    """
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


# Re-export for tests and intra-service helpers.
__all__ = [
    "EmbeddingUnavailable",
    "RetrievedChunk",
    "format_chunks",
    "is_enabled",
    "retrieve",
]
