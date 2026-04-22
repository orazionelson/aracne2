"""Ollama embeddings client.

Calls the ``/api/embeddings`` endpoint of the configured Ollama server to
turn text into dense vectors. Embeddings live separately from the chat
endpoint: they can use a different model (``ai_rag_embedding_model``)
pulled once on the Ollama volume.
"""

from __future__ import annotations

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

logger = structlog.get_logger()


class EmbeddingUnavailable(RuntimeError):
    """Raised when the embedding provider cannot be reached or the response
    is not a valid vector. Callers should treat RAG as unavailable and fall
    back to the raw prompt (without retrieved context)."""


async def _read_setting(db: AsyncSession, key: str, default: str) -> str:
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    return row.value if row and row.value else default


async def embed_text(db: AsyncSession, text: str) -> list[float]:
    """Return the embedding vector for a single piece of text.

    Uses the same Ollama server as the chat provider (``ai_ollama_base_url``)
    but the dedicated embedding model (``ai_rag_embedding_model``). Raises
    EmbeddingUnavailable on transport or protocol errors.
    """
    base_url = await _read_setting(db, "ai_ollama_base_url", "http://ollama:11434")
    model = await _read_setting(db, "ai_rag_embedding_model", "bge-m3")

    url = f"{base_url.rstrip('/')}/api/embeddings"
    payload = {"model": model, "prompt": text}
    # Embedding calls are short (one text at a time) — keep timeouts tight
    # so a dead embedder does not stall the whole request path.
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if not resp.is_success:
                raise EmbeddingUnavailable(
                    f"embedding HTTP {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise EmbeddingUnavailable(str(exc)) from exc

    vector = data.get("embedding")
    if not isinstance(vector, list) or not vector:
        raise EmbeddingUnavailable(f"unexpected embedding payload: {data!r}")
    return [float(x) for x in vector]
