"""Shared helpers for HTTP file uploads.

The naïve ``await file.read()`` reads up to nginx's request-body cap
(50 MB) into memory before the per-handler size check has a chance to
run. With the global rate limit of 200 req/min that's a cheap
authenticated-DoS vector: a single account can drive ~10 GB/min of
memory pressure through the avatar / media endpoints.

``read_capped`` reads in 64 KB chunks and aborts as soon as the
running total exceeds *max_bytes*, so the buffered allocation stays
bounded by *max_bytes + chunk_size* regardless of body size.
"""

from __future__ import annotations

from fastapi import UploadFile

from app.core.exceptions import DomainValidationError

_CHUNK = 64 * 1024


async def read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read *file* into memory, raising ``FILE_TOO_LARGE`` early on overshoot.

    Returns the full payload when it fits within *max_bytes*. The
    remaining body is left unread on the stream — Starlette will close
    the connection when the response is sent.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise DomainValidationError(
                code="FILE_TOO_LARGE",
                message=(
                    f"Upload exceeds the {max_bytes // (1024 * 1024)} MB limit"
                    if max_bytes >= 1024 * 1024
                    else f"Upload exceeds the {max_bytes // 1024} KB limit"
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)
