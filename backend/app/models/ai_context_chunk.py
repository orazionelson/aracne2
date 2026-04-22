"""AiContextChunk — a text chunk with its embedding, indexed for RAG.

Lives in the pgvector DB, not the main platform DB. Keep the schema small
and denormalised: retrieval is a single read per query and we never JOIN
with platform tables. Provenance fields (``source_type``, ``source_id``,
``chunk_index``, ``metadata``) carry enough context to reconstruct a
citation without a join.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.pgvector import PgvectorBase

# bge-m3 produces 1024-dim embeddings. If we change the default embedding
# model to a different dimension we must drop + rebuild the table.
EMBEDDING_DIM = 1024


def _now() -> datetime:
    return datetime.now(UTC)


class AiContextChunk(PgvectorBase):
    __tablename__ = "ai_context_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Where the chunk came from: "tei_p5", "schema", "collection_doc", …
    # Free-form short identifier; kept as string to avoid a migration when
    # new source types are added.
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Identifier of the originating resource within the source type. For
    # tei_p5 it is the section slug (e.g. "DS-metadata-fileDesc"); for
    # collection documents it is "<collection_slug>/<filename>".
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    # Ordinal of this chunk within the source resource (0-based). Lets us
    # reassemble contiguous chunks if needed.
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=False
    )
    chunk_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        # HNSW index on cosine distance — the usual choice for semantic
        # retrieval. Build parameters left at pgvector defaults (m=16,
        # ef_construction=64); tune only if recall/latency becomes an issue.
        Index(
            "ix_ai_context_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_ai_context_chunks_source",
            "source_type",
            "source_id",
            "chunk_index",
        ),
    )
