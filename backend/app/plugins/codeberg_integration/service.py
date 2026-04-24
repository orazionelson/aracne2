"""Codeberg plugin — service layer.

Owns the CRUD for ``codeberg_collection_links`` rows, resolves the
effective PAT (per-link override > global plugin PAT), builds a
``DepositManifest`` from the collection's TEI files and invokes the
shared git-forge orchestrator.

Push direction is unconditional — every push creates one commit with
every TEI file in the collection. The orchestrator side (adapter)
is responsible for distinguishing ``create`` vs. ``update`` operations
against the remote tree.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import encrypt_value
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.db.existdb import ExistDBClient
from app.models.collection import Collection
from app.plugins._lib.git_forge.codeberg import CodebergAdapter
from app.plugins._lib.git_forge.errors import (
    AuthFailed,
    Forbidden,
    GitForgeError,
    PushConflict,
    RateLimited,
    RepoNotFound,
    UpstreamError,
)
from app.plugins._lib.git_forge.models import (
    DepositFile,
    DepositManifest,
    RepoRef,
)
from app.plugins._lib.git_forge.push import (
    TokenSources,
    push_manifest,
    resolve_token,
)
from app.plugins.codeberg_integration.models import CodebergCollectionLink
from app.plugins.codeberg_integration.schemas import (
    CodebergLinkCreate,
    CodebergLinkResponse,
    CodebergPushResponse,
)
from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()

_PAT_SETTING_KEY = "codeberg_integration_pat"
_COMMITTER_NAME = "Aracne2"
_COMMITTER_EMAIL = "aracne2@localhost"


# ── Config (global PAT) ────────────────────────────────────────────────────


async def get_config_pat_set(db: AsyncSession) -> bool:
    """True when the global ``codeberg_integration_pat`` is populated."""
    value = (await get_decrypted_setting(db, _PAT_SETTING_KEY) or "").strip()
    return bool(value)


async def update_config_pat(db: AsyncSession, plaintext: str | None) -> None:
    """Set the global PAT; empty string clears it; ``None`` is a no-op
    (handled by the router when the field is absent)."""
    if plaintext is None:
        return
    from app.models.system_setting import SystemSetting

    row = await db.get(SystemSetting, _PAT_SETTING_KEY)
    if row is None:
        raise DomainValidationError(
            "SETTING_MISSING",
            f"Setting '{_PAT_SETTING_KEY}' missing — did migration 0060 run?",
        )
    value = plaintext.strip()
    row.value = encrypt_value(value, app_settings.jwt_secret) if value else ""
    await db.flush()


# ── Link CRUD ──────────────────────────────────────────────────────────────


async def _get_collection_by_slug(
    db: AsyncSession, slug: str,
) -> Collection:
    col = await db.scalar(
        select(Collection).where(Collection.slug == slug)
    )
    if col is None:
        raise NotFoundError(f"Collection '{slug}' not found.")
    return col


async def _get_link(
    db: AsyncSession, collection_id: uuid.UUID,
) -> CodebergCollectionLink | None:
    return await db.scalar(
        select(CodebergCollectionLink).where(
            CodebergCollectionLink.collection_id == collection_id,
        )
    )


def _to_response(link: CodebergCollectionLink) -> CodebergLinkResponse:
    return CodebergLinkResponse(
        base_url=link.base_url,
        repo_owner=link.repo_owner,
        repo_name=link.repo_name,
        branch=link.branch,
        pat_override_set=bool(link.pat_override),
        last_push_sha=link.last_push_sha,
        last_push_at=link.last_push_at,
        initialized_at=link.initialized_at,
        initialized_from_sha=link.initialized_from_sha,
        html_url=f"{link.base_url}/{link.repo_owner}/{link.repo_name}",
    )


async def get_link(
    db: AsyncSession, slug: str,
) -> CodebergLinkResponse:
    col = await _get_collection_by_slug(db, slug)
    link = await _get_link(db, col.id)
    if link is None:
        raise NotFoundError(
            f"Collection '{slug}' is not linked to a Codeberg repository.",
        )
    return _to_response(link)


async def upsert_link(
    db: AsyncSession, slug: str, data: CodebergLinkCreate,
) -> CodebergLinkResponse:
    col = await _get_collection_by_slug(db, slug)
    link = await _get_link(db, col.id)
    if link is None:
        link = CodebergCollectionLink(collection_id=col.id)
        db.add(link)

    link.base_url = data.base_url
    link.repo_owner = data.repo_owner
    link.repo_name = data.repo_name
    link.branch = data.branch

    # pat_override semantics:
    #   None  → leave existing value alone
    #   ""    → clear (use global PAT)
    #   else  → encrypt and store
    if data.pat_override is not None:
        if data.pat_override == "":
            link.pat_override = None
        else:
            link.pat_override = encrypt_value(
                data.pat_override.strip(), app_settings.jwt_secret,
            )

    await db.flush()
    return _to_response(link)


async def delete_link(db: AsyncSession, slug: str) -> None:
    col = await _get_collection_by_slug(db, slug)
    link = await _get_link(db, col.id)
    if link is None:
        # Idempotent: deleting a non-existent link is success.
        return
    await db.delete(link)
    await db.flush()


# ── Push ───────────────────────────────────────────────────────────────────


def _map_forge_error(exc: GitForgeError) -> DomainValidationError:
    """Translate a shared git-forge exception into a domain error with
    a stable code the HTTP layer can surface to the admin UI."""
    if isinstance(exc, AuthFailed):
        return DomainValidationError(
            "FORGE_AUTH_FAILED",
            "Codeberg rejected the token. Check the PAT and its scopes.",
        )
    if isinstance(exc, Forbidden):
        return DomainValidationError(
            "FORGE_FORBIDDEN",
            "The PAT is valid but lacks the scope for this operation "
            "(needs 'write:repository').",
        )
    if isinstance(exc, RepoNotFound):
        return DomainValidationError(
            "FORGE_REPO_NOT_FOUND",
            "Codeberg could not find that owner/name pair or the PAT "
            "cannot see it.",
        )
    if isinstance(exc, PushConflict):
        return DomainValidationError(
            "FORGE_PUSH_CONFLICT",
            "Branch or file SHA moved under us — retry the push.",
        )
    if isinstance(exc, RateLimited):
        return DomainValidationError(
            "FORGE_RATE_LIMITED",
            "Codeberg rate-limited the request. Wait and retry.",
        )
    return DomainValidationError(
        "FORGE_UPSTREAM_ERROR",
        f"Unexpected upstream error: {exc}",
    )


async def _collect_manifest(
    existdb: ExistDBClient,
    *,
    slug: str,
    branch: str,
    message: str,
) -> DepositManifest:
    filenames = await existdb.list_collection(slug)
    filenames.sort()
    files: list[DepositFile] = []
    for filename in filenames:
        content = await existdb.get_document(slug, filename)
        files.append(
            DepositFile(path=f"documents/{filename}", content=content),
        )
    return DepositManifest(
        files=files,
        branch=branch,
        commit_message=message,
        committer_name=_COMMITTER_NAME,
        committer_email=_COMMITTER_EMAIL,
    )


async def push_collection(
    db: AsyncSession,
    existdb: ExistDBClient,
    *,
    slug: str,
    message: str | None = None,
    adapter: Any | None = None,
    transport: Any | None = None,
) -> CodebergPushResponse:
    """Push every TEI file in ``slug`` to the linked Codeberg repo in
    a single commit.

    ``adapter`` and ``transport`` are injectable for tests; production
    code always uses :class:`CodebergAdapter` with a real network
    client.
    """
    col = await _get_collection_by_slug(db, slug)
    link = await _get_link(db, col.id)
    if link is None:
        raise NotFoundError(
            f"Collection '{slug}' is not linked to a Codeberg repository.",
        )

    # Resolve the effective PAT.
    global_cipher = await get_decrypted_setting(db, _PAT_SETTING_KEY)
    # ``get_decrypted_setting`` returns the *decrypted* value — but
    # the resolver needs ciphertext so per-link and global can share
    # the same path. Re-encrypt in memory so the helper stays pure.
    # (Slightly wasteful; refactoring the settings service is out of
    # scope for Phase 1.)
    if global_cipher:
        global_cipher = encrypt_value(
            global_cipher, app_settings.jwt_secret,
        )
    token = resolve_token(
        TokenSources(
            override_ciphertext=link.pat_override,
            global_ciphertext=global_cipher,
            jwt_secret=app_settings.jwt_secret,
        )
    )
    if not token:
        raise DomainValidationError(
            "FORGE_PAT_MISSING",
            "No PAT configured. Set a global PAT in the plugin config "
            "or a per-link override on this collection.",
        )

    effective_message = (
        (message or "").strip()
        or f"Aracne2 sync: {col.title}"
    )
    manifest = await _collect_manifest(
        existdb, slug=slug, branch=link.branch, message=effective_message,
    )
    if not manifest.files:
        raise ConflictError(
            "Collection has no documents — nothing to push.",
        )

    adapter = adapter or CodebergAdapter()
    repo = RepoRef(
        base_url=link.base_url,
        owner=link.repo_owner,
        name=link.repo_name,
    )
    try:
        result = await push_manifest(
            adapter=adapter,
            repo=repo,
            manifest=manifest,
            token=token,
            transport=transport,
        )
    except GitForgeError as exc:
        logger.warning(
            "codeberg_push_failed", slug=slug, error=str(exc),
        )
        raise _map_forge_error(exc) from exc

    link.last_push_sha = result.sha
    link.last_push_at = result.committed_at or datetime.now(UTC)
    await db.flush()

    return CodebergPushResponse(
        sha=result.sha,
        committed_at=link.last_push_at,
        html_url=result.html_url,
        file_count=len(manifest.files),
    )
