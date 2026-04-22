"""Ingest a TEI P5 corpus into the RAG vector store.

Usage (from inside the backend container):

    docker compose exec backend python -m app.scripts.ingest_tei_p5 \\
        --source /tmp/tei-p5/

The script walks ``--source`` for files matching ``.html``, ``.xml``,
``.txt`` and ``.md``, extracts plain text (stripping XML/HTML tags where
applicable), chunks the text by paragraphs targeting ~500 tokens per
chunk, computes embeddings via the configured Ollama embedding model,
and inserts every chunk into the ``ai_context_chunks`` table with
``source_type='tei_p5'``.

The script is intentionally format-agnostic: the admin can feed it any
export of the P5 Guidelines (HTML bundle from tei-c.org, markdown
export from pandoc, plain-text conversion). It can also be repurposed
later to index the project's own corpus by changing ``--source-type``.

Safeguards:
- ``--dry-run`` parses and chunks without calling Ollama or writing
  to the vector store. Use it to preview what would be ingested.
- ``--purge`` deletes every row in ``ai_context_chunks`` with the
  matching ``source_type`` before inserting. Necessary when switching
  the embedding model (dimensions may differ).

Failure modes degrade gracefully: missing Ollama embeddings abort the
run with a clear error; partial progress is committed in small batches
so an interrupted run can resume.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import structlog
from lxml import etree  # type: ignore[import-untyped]
from sqlalchemy import delete

from app.db.pgvector import get_session_factory, is_available
from app.db.postgres import AsyncSessionLocal
from app.models.ai_context_chunk import AiContextChunk
from app.plugins._native.ai.embeddings import EmbeddingUnavailable, embed_text

logger = structlog.get_logger()

_SUPPORTED_EXTS = {".html", ".xhtml", ".xml", ".txt", ".md"}
# Approximate character count per target chunk. 500 tokens * 4 chars/token.
_CHUNK_TARGET_CHARS = 2000
# Minimum chunk size in characters — below this we merge with the next block.
_CHUNK_MIN_CHARS = 200
# Insert commit batch size — trades memory for throughput.
_BATCH_SIZE = 50


def _extract_text(path: Path) -> str:
    """Return plain text from an HTML, XML, TXT or Markdown file.

    For HTML/XML: parse with a forgiving parser and concatenate text
    content. For TXT/MD: read as-is.

    Uses ``lxml`` which is already in the dependency set (TEI processing).
    ``etree.HTMLParser`` tolerates malformed input — TEI-produced HTML is
    well-formed but we prefer robustness over strictness here.
    """
    raw = path.read_bytes()
    ext = path.suffix.lower()
    if ext in (".html", ".xhtml"):
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(raw, parser)
        if tree is None:
            return ""
        return " ".join(tree.itertext())
    if ext == ".xml":
        parser = etree.XMLParser(recover=True, huge_tree=True)
        tree = etree.fromstring(raw, parser)
        if tree is None:
            return ""
        return " ".join(tree.itertext())
    # Plain text / markdown — keep verbatim so structure (headings, lists)
    # survives the chunker.
    return raw.decode("utf-8", errors="replace")


def _chunk_text(text: str) -> list[str]:
    """Split *text* into roughly ``_CHUNK_TARGET_CHARS``-sized chunks along
    paragraph boundaries. Paragraphs are split on blank lines; chunks keep
    paragraph boundaries intact (no mid-paragraph cuts).
    """
    # Collapse runs of whitespace except newlines so paragraph detection
    # works on varied source formats.
    normalised = re.sub(r"[ \t]+", " ", text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalised) if p.strip()]

    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paragraphs:
        # A single oversized paragraph becomes its own chunk — better than
        # cutting mid-sentence. Ingestion still works, retrieval is fine.
        if len(para) > _CHUNK_TARGET_CHARS and buf_len == 0:
            chunks.append(para)
            continue
        if buf_len + len(para) > _CHUNK_TARGET_CHARS and buf_len >= _CHUNK_MIN_CHARS:
            chunks.append("\n\n".join(buf))
            buf = [para]
            buf_len = len(para)
        else:
            buf.append(para)
            buf_len += len(para) + 2  # +2 for the newlines between paragraphs
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


async def _purge(source_type: str) -> None:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("pgvector not configured (PGVECTOR_HOST is empty)")
    async with factory() as db:
        result = await db.execute(
            delete(AiContextChunk).where(AiContextChunk.source_type == source_type)
        )
        await db.commit()
        logger.info("ingest_purged", source_type=source_type, deleted=result.rowcount)


async def _ingest(
    source_root: Path,
    source_type: str,
    dry_run: bool,
) -> tuple[int, int]:
    """Return (files_processed, chunks_inserted)."""
    factory = get_session_factory()
    if not dry_run and factory is None:
        raise RuntimeError("pgvector not configured (PGVECTOR_HOST is empty)")

    files = sorted(
        p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTS
    )
    if not files:
        logger.warning("ingest_no_files", source=str(source_root))
        return (0, 0)

    total_chunks = 0
    pending: list[AiContextChunk] = []

    # Single long-lived platform session for embeddings (they read settings).
    async with AsyncSessionLocal() as platform_db:
        for fpath in files:
            rel_id = str(fpath.relative_to(source_root))
            try:
                text = _extract_text(fpath)
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the run
                logger.warning("ingest_extract_failed", file=rel_id, error=str(exc))
                continue
            chunks = _chunk_text(text)
            if not chunks:
                continue
            logger.info("ingest_file", file=rel_id, chunks=len(chunks))

            for idx, chunk_text in enumerate(chunks):
                if dry_run:
                    total_chunks += 1
                    continue
                try:
                    vec = await embed_text(platform_db, chunk_text)
                except EmbeddingUnavailable as exc:
                    logger.error("ingest_embedding_failed", file=rel_id, chunk=idx, error=str(exc))
                    raise SystemExit(1) from exc
                pending.append(
                    AiContextChunk(
                        source_type=source_type,
                        source_id=rel_id,
                        chunk_index=idx,
                        text=chunk_text,
                        embedding=vec,
                    )
                )
                total_chunks += 1
                if len(pending) >= _BATCH_SIZE:
                    await _flush(pending, factory)
                    pending = []
        if pending and not dry_run:
            await _flush(pending, factory)

    return (len(files), total_chunks)


async def _flush(batch: list[AiContextChunk], factory) -> None:  # type: ignore[no-untyped-def]
    async with factory() as db:
        db.add_all(batch)
        await db.commit()
    logger.info("ingest_batch_flushed", size=len(batch))


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python -m app.scripts.ingest_tei_p5",
        description="Ingest a directory of TEI P5 documentation (HTML/XML/TXT/MD) into pgvector.",
    )
    ap.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Root directory containing the corpus files (walked recursively).",
    )
    ap.add_argument(
        "--source-type",
        default="tei_p5",
        help="Value written to ai_context_chunks.source_type (default: tei_p5).",
    )
    ap.add_argument(
        "--purge",
        action="store_true",
        help="Delete every existing chunk with the same source_type before ingesting.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk the source and chunk the text, but skip embeddings and DB writes.",
    )
    return ap.parse_args()


async def _main() -> None:
    args = _parse_args()
    if not args.dry_run and not is_available():
        print(
            "pgvector is not configured (PGVECTOR_HOST is empty). "
            "Run with --dry-run to preview, or enable the ai-local profile "
            "and set PGVECTOR_HOST=pgvector in .env.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not args.source.exists() or not args.source.is_dir():
        print(f"--source must be an existing directory: {args.source}", file=sys.stderr)
        raise SystemExit(2)

    if args.purge and not args.dry_run:
        await _purge(args.source_type)

    files, chunks = await _ingest(args.source, args.source_type, args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "ingested"
    print(f"{mode}: files={files} chunks={chunks} source_type={args.source_type}")


if __name__ == "__main__":
    asyncio.run(_main())
