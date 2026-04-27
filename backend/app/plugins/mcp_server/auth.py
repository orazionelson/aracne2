"""MCP bearer-token auth — resolves to (token row, corpus, collection ids).

The plugin's HTTP entrypoint extracts ``Authorization: Bearer <token>``
from the request, looks it up via ``corpora.resolve_token`` (bcrypt
verify against every non-revoked row), and returns the matched corpus
+ a frozen list of collection ids the token is allowed to read.

A failure to resolve or a missing header → ``McpAuthError`` which the
JSON-RPC layer turns into a `-32001` "Unauthorized" response.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.corpus import Corpus, McpToken
from app.services.corpora import resolve_token


class McpAuthError(Exception):
    """Raised when a request cannot be authorised."""

    def __init__(self, message: str, *, code: str = "UNAUTHORIZED") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class McpAuthContext:
    """Resolved bearer-token context handed to every tool / resource."""

    token: McpToken
    corpus: Corpus
    collection_ids: frozenset[uuid.UUID]


async def authenticate(request: Request, db: AsyncSession) -> McpAuthContext:
    """Validate the request's bearer token and load its corpus scope.

    Returns a frozen ``McpAuthContext`` tools/resources can read freely.
    Raises ``McpAuthError`` on missing / malformed / unknown / revoked
    tokens — the caller maps the exception to a JSON-RPC error.
    """
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        raise McpAuthError("Missing Authorization header.")
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise McpAuthError("Authorization header must be 'Bearer <token>'.")
    plaintext = parts[1].strip()
    if not plaintext:
        raise McpAuthError("Empty bearer token.")

    resolved = await resolve_token(db, plaintext)
    if resolved is None:
        raise McpAuthError("Token unknown or revoked.")
    token, corpus = resolved
    collection_ids = frozenset(c.id for c in corpus.collections)
    return McpAuthContext(token=token, corpus=corpus, collection_ids=collection_ids)
