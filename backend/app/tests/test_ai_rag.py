"""Unit tests for the RAG retrieval pipeline.

We mock out the embedding call (Ollama HTTP) and the pgvector session
factory so the tests run against the SQLite in-memory fixture used by the
rest of the suite. This exercises the service wiring and the fail-soft
branches without requiring a live vector store.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting
from app.plugins._native.ai import rag
from app.plugins._native.ai.embeddings import EmbeddingUnavailable
from app.plugins._native.ai.service import _augment_with_rag


async def _set(db: AsyncSession, key: str, value: str, type_: str = "string") -> None:
    db.add(SystemSetting(key=key, value=value, type=type_))
    await db.flush()


@pytest.mark.asyncio
async def test_augment_noop_when_template_has_no_rag_placeholder(
    db_session: AsyncSession,
) -> None:
    """Templates without {rag_context} must not trigger any retrieval work."""
    with patch("app.plugins._native.ai.rag.is_enabled", new=AsyncMock()) as is_enabled:
        result = await _augment_with_rag(
            db_session, "Plain prompt with {selection}", {"selection": "x"}
        )
    assert result == {"selection": "x"}
    is_enabled.assert_not_called()


@pytest.mark.asyncio
async def test_augment_injects_empty_when_rag_disabled(
    db_session: AsyncSession,
) -> None:
    """Setting off -> placeholder substituted with "" so the template still
    renders without a KeyError."""
    await _set(db_session, "ai_rag_enabled", "false", "bool")
    result = await _augment_with_rag(
        db_session, "Prompt {rag_context} end", {"selection": "query text"}
    )
    assert result["rag_context"] == ""
    assert result["selection"] == "query text"


@pytest.mark.asyncio
async def test_augment_injects_empty_when_pgvector_unavailable(
    db_session: AsyncSession,
) -> None:
    """Enabled but pgvector not configured -> still fails soft with ""."""
    await _set(db_session, "ai_rag_enabled", "true", "bool")
    with patch(
        "app.db.pgvector.get_session_factory", return_value=None
    ), patch(
        "app.plugins._native.ai.rag.is_available", return_value=False
    ):
        result = await _augment_with_rag(
            db_session, "Prompt {rag_context}", {"selection": "q"}
        )
    assert result["rag_context"] == ""


@pytest.mark.asyncio
async def test_augment_injects_empty_when_retrieval_raises(
    db_session: AsyncSession,
) -> None:
    """Retrieval failures must never propagate — the base prompt still runs."""
    await _set(db_session, "ai_rag_enabled", "true", "bool")

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[rag.RetrievedChunk]:
        raise RuntimeError("boom")

    class _FakeFactory:
        def __call__(self) -> "_FakeFactory":
            return self

        async def __aenter__(self) -> "_FakeFactory":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    with patch("app.plugins._native.ai.rag.is_available", return_value=True), \
         patch("app.db.pgvector.get_session_factory", return_value=_FakeFactory()), \
         patch("app.plugins._native.ai.rag.retrieve", new=_fake_retrieve):
        result = await _augment_with_rag(
            db_session, "Prompt {rag_context}", {"selection": "q"}
        )
    assert result["rag_context"] == ""


@pytest.mark.asyncio
async def test_embed_text_raises_embedding_unavailable_on_http_error(
    db_session: AsyncSession,
) -> None:
    """A non-2xx from Ollama must surface as EmbeddingUnavailable, not a
    raw httpx exception the caller would have to catch separately."""
    from app.plugins._native.ai.embeddings import embed_text

    class _Resp:
        is_success = False
        status_code = 500
        text = "boom"

    class _Client:
        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        async def post(self, *a: object, **kw: object) -> _Resp:
            return _Resp()

    with patch("app.plugins._native.ai.embeddings.httpx.AsyncClient", return_value=_Client()):
        with pytest.raises(EmbeddingUnavailable):
            await embed_text(db_session, "hello")


@pytest.mark.asyncio
async def test_augment_injects_formatted_chunks_on_successful_retrieval(
    db_session: AsyncSession,
) -> None:
    """Happy path: retrieval returns chunks, they are formatted into the
    placeholder with source prefixes and separated by horizontal rules."""
    await _set(db_session, "ai_rag_enabled", "true", "bool")

    fake_chunks = [
        rag.RetrievedChunk(
            text="TEI P5 says title lives in titleStmt",
            source_type="tei_p5",
            source_id="DS-metadata-fileDesc",
            chunk_index=0,
            score=0.91,
        ),
        rag.RetrievedChunk(
            text="Every <author> child is optional",
            source_type="tei_p5",
            source_id="DS-metadata-titleStmt",
            chunk_index=1,
            score=0.83,
        ),
    ]

    async def _fake_retrieve(*args: object, **kwargs: object) -> list[rag.RetrievedChunk]:
        return fake_chunks

    class _FakeFactory:
        def __call__(self) -> "_FakeFactory":
            return self

        async def __aenter__(self) -> "_FakeFactory":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    with patch("app.plugins._native.ai.rag.is_available", return_value=True), \
         patch("app.db.pgvector.get_session_factory", return_value=_FakeFactory()), \
         patch("app.plugins._native.ai.rag.retrieve", new=_fake_retrieve):
        result = await _augment_with_rag(
            db_session,
            "Prompt:\n{rag_context}\n\nQuestion: {selection}",
            {"selection": "How do I encode a title?"},
        )
    assert "tei_p5:DS-metadata-fileDesc#0" in result["rag_context"]
    assert "title lives in titleStmt" in result["rag_context"]
    assert "tei_p5:DS-metadata-titleStmt#1" in result["rag_context"]
    assert "---" in result["rag_context"]


def test_format_chunks_empty_returns_empty_string() -> None:
    assert rag.format_chunks([]) == ""


def test_vec_literal_formats_pgvector_array() -> None:
    from app.plugins._native.ai.rag import _vec_literal

    assert _vec_literal([0.1, 0.25, -0.5]) == "[0.100000,0.250000,-0.500000]"
