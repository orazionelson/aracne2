"""Corpus + MCP token management — Admin only.

A corpus is a thematic grouping of public collections. The only
consumer today is the MCP server plugin: a token issued for corpus
X grants programmatic read access scoped to X's collections.

All endpoints require ``Admin`` because issuing/revoking tokens
modifies the platform's authorization surface — not delegable to
EditorInChief.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.corpora import (
    CorpusCollectionItem,
    CorpusCreate,
    CorpusResponse,
    CorpusUpdate,
    McpTokenCreate,
    McpTokenCreated,
    McpTokenResponse,
)
from app.services.corpora import (
    create_corpus as svc_create_corpus,
    delete_corpus as svc_delete_corpus,
    get_corpus as svc_get_corpus,
    issue_token as svc_issue_token,
    list_corpora as svc_list_corpora,
    list_tokens as svc_list_tokens,
    revoke_token as svc_revoke_token,
    update_corpus as svc_update_corpus,
)


router = APIRouter(prefix="/corpora", tags=["corpora"])

_admin = Depends(require_role(min_role="Admin"))


def _build_corpus_response(corpus, token_count: int) -> CorpusResponse:
    return CorpusResponse(
        id=corpus.id,
        name=corpus.name,
        description=corpus.description,
        created_at=corpus.created_at,
        updated_at=corpus.updated_at,
        collections=[
            CorpusCollectionItem(
                id=c.id,
                slug=c.slug,
                title=c.title,
                is_public=c.is_public,
                status=c.status.value if hasattr(c.status, "value") else str(c.status),
            )
            for c in corpus.collections
        ],
        token_count=token_count,
    )


def _site_base_url(request: Request) -> str:
    """Build the absolute origin (scheme + host) seen by the caller.

    Used to pre-fill the Claude Desktop snippet returned at token
    creation. Trailing slash stripped — the snippet appends the path.
    """
    return f"{request.url.scheme}://{request.url.netloc}"


# ── Corpus CRUD ───────────────────────────────────────────────────────────────


@router.get("")
async def list_corpora(
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[CorpusResponse]]:
    rows = await svc_list_corpora(db)
    return DataResponse(
        data=[_build_corpus_response(c, n) for c, n in rows]
    )


@router.post("", status_code=201)
async def create_corpus(
    body: CorpusCreate,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CorpusResponse]:
    corpus, count = await svc_create_corpus(
        db,
        name=body.name,
        description=body.description,
        collection_ids=body.collection_ids,
    )
    return DataResponse(data=_build_corpus_response(corpus, count))


@router.get("/{corpus_id}")
async def get_corpus(
    corpus_id: uuid.UUID,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CorpusResponse]:
    corpus, count = await svc_get_corpus(db, corpus_id)
    return DataResponse(data=_build_corpus_response(corpus, count))


@router.put("/{corpus_id}")
async def update_corpus(
    corpus_id: uuid.UUID,
    body: CorpusUpdate,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CorpusResponse]:
    corpus, count = await svc_update_corpus(
        db,
        corpus_id,
        name=body.name,
        description=body.description,
        collection_ids=body.collection_ids,
    )
    return DataResponse(data=_build_corpus_response(corpus, count))


@router.delete("/{corpus_id}", status_code=204)
async def delete_corpus(
    corpus_id: uuid.UUID,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await svc_delete_corpus(db, corpus_id)


# ── MCP token sub-resource ────────────────────────────────────────────────────


@router.get("/{corpus_id}/tokens")
async def list_tokens(
    corpus_id: uuid.UUID,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[McpTokenResponse]]:
    rows = await svc_list_tokens(db, corpus_id)
    return DataResponse(
        data=[
            McpTokenResponse(
                id=r.id,
                label=r.label,
                created_at=r.created_at,
                last_used_at=r.last_used_at,
                revoked_at=r.revoked_at,
            )
            for r in rows
        ]
    )


@router.post("/{corpus_id}/tokens", status_code=201)
async def issue_token(
    corpus_id: uuid.UUID,
    body: McpTokenCreate,
    request: Request,
    actor: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[McpTokenCreated]:
    """Generate a new MCP bearer token for *corpus_id*.

    The plaintext is returned **once** — copy it now or revoke and
    re-issue. The accompanying snippet is pre-filled with the request's
    origin so the admin can hand it to the editor as-is.
    """
    row, plaintext, snippet = await svc_issue_token(
        db,
        corpus_id=corpus_id,
        label=body.label,
        actor=actor,
        base_url=_site_base_url(request),
    )
    return DataResponse(
        data=McpTokenCreated(
            id=row.id,
            label=row.label,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            revoked_at=row.revoked_at,
            plaintext=plaintext,
            claude_desktop_snippet=snippet,
        )
    )


@router.delete("/{corpus_id}/tokens/{token_id}", status_code=204)
async def revoke_token(
    corpus_id: uuid.UUID,
    token_id: uuid.UUID,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await svc_revoke_token(db, corpus_id, token_id)
