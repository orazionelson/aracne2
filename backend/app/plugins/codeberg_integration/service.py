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

import posixpath
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from defusedxml import ElementTree as _DefusedET
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
from app.models.website import BuildStatus, RenderingMode, Website
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
    InitializeBundle,
    RepoRef,
)
from app.plugins._lib.git_forge.push import (
    TokenSources,
    push_manifest,
    resolve_token,
)
from app.plugins.codeberg_integration.models import (
    CodebergCollectionLink,
    CodebergWebsiteLink,
)
from app.plugins.codeberg_integration.schemas import (
    CodebergInitializeResponse,
    CodebergLinkCreate,
    CodebergLinkResponse,
    CodebergPushResponse,
    CodebergWebsiteLinkCreate,
    CodebergWebsiteLinkResponse,
    CodebergWebsitePushResponse,
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


# ── Initialize (Phase 2 — forge → empty collection) ───────────────────────

_INITIALIZE_MAX_FILES = 500
_INITIALIZE_MAX_BYTES_PER_FILE = 10 * 1024 * 1024  # 10 MB
_INITIALIZE_DOCS_PREFIX = "documents/"


def _select_importable_files(
    bundle: InitializeBundle,
) -> list[DepositFile]:
    """Filter an InitializeBundle down to importable TEI XML files.

    Keeps only ``*.xml`` entries. Strips a leading ``documents/``
    prefix when present (so a repo that was previously pushed by
    Aracne2 round-trips cleanly). Raises DomainValidationError if
    any filename would collide after flattening — Aracne2's
    per-collection storage is flat, so nested XML with duplicate
    basenames cannot be represented.
    """
    seen: dict[str, str] = {}  # basename → original path
    picked: list[DepositFile] = []
    for entry in bundle.files:
        path = entry.path
        if not path.lower().endswith(".xml"):
            continue
        # Strip optional documents/ prefix; otherwise use the basename
        # of whatever path the file lives under.
        if path.startswith(_INITIALIZE_DOCS_PREFIX):
            basename = path[len(_INITIALIZE_DOCS_PREFIX):]
        else:
            basename = posixpath.basename(path)
        if not basename or basename.startswith("."):
            continue
        if len(entry.content) > _INITIALIZE_MAX_BYTES_PER_FILE:
            raise DomainValidationError(
                "FORGE_INIT_FILE_TOO_LARGE",
                f"'{path}' exceeds the {_INITIALIZE_MAX_BYTES_PER_FILE} "
                f"byte import limit per file.",
            )
        if basename in seen:
            raise DomainValidationError(
                "FORGE_INIT_NAME_COLLISION",
                f"Filename collision on import: '{basename}' appears in "
                f"both '{seen[basename]}' and '{path}'. Flatten the repo "
                f"before importing.",
            )
        seen[basename] = path
        picked.append(DepositFile(path=basename, content=entry.content))

    if len(picked) > _INITIALIZE_MAX_FILES:
        raise DomainValidationError(
            "FORGE_INIT_TOO_MANY_FILES",
            f"Repository contains {len(picked)} XML files — exceeds the "
            f"{_INITIALIZE_MAX_FILES} import ceiling. Use the CLI tool "
            f"for larger corpora.",
        )
    return picked


def _validate_wellformed(file_: DepositFile) -> None:
    """Parse with defusedxml; reject malformed XML before it reaches eXist."""
    try:
        _DefusedET.fromstring(file_.content)
    except Exception as exc:  # defusedxml raises a variety of types
        raise DomainValidationError(
            "FORGE_INIT_MALFORMED_XML",
            f"'{file_.path}' is not well-formed XML: {exc}",
        ) from exc


async def initialize_collection(
    db: AsyncSession,
    existdb: ExistDBClient,
    *,
    slug: str,
    adapter: Any | None = None,
    transport: Any | None = None,
) -> CodebergInitializeResponse:
    """One-shot import: copy every ``*.xml`` file from the linked
    Codeberg repository into an *empty* Aracne2 collection.

    Guards:
      - Collection must exist and be empty (zero documents).
      - A Codeberg link must exist for the collection.
      - The link must not already have an ``initialized_at`` timestamp
        (initialize is permanently disabled once it has run once or
        once any document has been written through other means).

    Each imported file is parsed with ``defusedxml`` before being
    written to eXist-db; malformed entries abort the whole import so
    a partially-populated collection never results.
    """
    col = await _get_collection_by_slug(db, slug)
    link = await _get_link(db, col.id)
    if link is None:
        raise NotFoundError(
            f"Collection '{slug}' is not linked to a Codeberg repository.",
        )
    if link.initialized_at is not None:
        raise ConflictError(
            f"Collection '{slug}' has already been initialized from "
            f"Codeberg — push is the only allowed direction from now on.",
        )

    # Zero-document precondition: check eXist, not ORM (the collection
    # may or may not have had a Postgres counter, but eXist is the
    # authoritative store for documents).
    existing = await existdb.list_collection(slug)
    if existing:
        raise ConflictError(
            f"Collection '{slug}' already contains {len(existing)} "
            f"document(s); Initialize requires a completely empty "
            f"collection.",
        )

    # Resolve the effective PAT (identical logic to push_collection).
    global_cipher = await get_decrypted_setting(db, _PAT_SETTING_KEY)
    if global_cipher:
        global_cipher = encrypt_value(global_cipher, app_settings.jwt_secret)
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

    adapter = adapter or CodebergAdapter()
    repo = RepoRef(
        base_url=link.base_url,
        owner=link.repo_owner,
        name=link.repo_name,
    )
    try:
        bundle = await adapter.initialize_bundle(
            repo=repo, branch=link.branch, token=token, transport=transport,
        )
    except GitForgeError as exc:
        logger.warning(
            "codeberg_initialize_failed", slug=slug, error=str(exc),
        )
        raise _map_forge_error(exc) from exc

    if not bundle.head_sha:
        raise ConflictError(
            f"Codeberg reports no commits on branch '{link.branch}' — "
            f"nothing to import."
        )

    importable = _select_importable_files(bundle)
    if not importable:
        raise ConflictError(
            "Repository contains no XML files to import.",
        )

    # Parse every file up-front; if any is malformed, bail before writing
    # a single byte to eXist so the collection stays empty.
    for f in importable:
        _validate_wellformed(f)

    # Ensure the eXist collection exists (create it on-demand — Aracne2
    # lazy-creates these when the first document arrives).
    if not await existdb.collection_exists(slug):
        await existdb.create_collection(slug)

    # Upload each file. If a write fails halfway through, we leave the
    # partially-written state in place for the operator to inspect —
    # Initialize is a one-shot and retrying requires manual cleanup.
    for f in importable:
        await existdb.put_document(slug, f.path, f.content)

    link.initialized_at = datetime.now(UTC)
    link.initialized_from_sha = bundle.head_sha
    await db.flush()

    return CodebergInitializeResponse(
        file_count=len(importable),
        head_sha=bundle.head_sha,
        initialized_at=link.initialized_at,
    )


# ── Website links ──────────────────────────────────────────────────────────

_WEBSITE_PUSH_MAX_FILES = 5000
_WEBSITE_PUSH_MAX_BYTES_PER_FILE = 25 * 1024 * 1024  # 25 MB (cover images, PDFs)


async def _get_website_by_slug(
    db: AsyncSession, slug: str,
) -> Website:
    row = await db.scalar(select(Website).where(Website.slug == slug))
    if row is None:
        raise NotFoundError(f"Website '{slug}' not found.")
    return row


async def _get_website_link(
    db: AsyncSession, website_id: uuid.UUID,
) -> CodebergWebsiteLink | None:
    return await db.scalar(
        select(CodebergWebsiteLink).where(
            CodebergWebsiteLink.website_id == website_id,
        )
    )


def _website_link_to_response(
    link: CodebergWebsiteLink,
) -> CodebergWebsiteLinkResponse:
    return CodebergWebsiteLinkResponse(
        base_url=link.base_url,
        repo_owner=link.repo_owner,
        repo_name=link.repo_name,
        branch=link.branch,
        pat_override_set=bool(link.pat_override),
        last_push_sha=link.last_push_sha,
        last_push_at=link.last_push_at,
        last_push_file_count=link.last_push_file_count,
        html_url=f"{link.base_url}/{link.repo_owner}/{link.repo_name}",
    )


async def get_website_link(
    db: AsyncSession, slug: str,
) -> CodebergWebsiteLinkResponse:
    website = await _get_website_by_slug(db, slug)
    link = await _get_website_link(db, website.id)
    if link is None:
        raise NotFoundError(
            f"Website '{slug}' is not linked to a Codeberg repository.",
        )
    return _website_link_to_response(link)


async def upsert_website_link(
    db: AsyncSession, slug: str, data: CodebergWebsiteLinkCreate,
) -> CodebergWebsiteLinkResponse:
    website = await _get_website_by_slug(db, slug)
    link = await _get_website_link(db, website.id)
    if link is None:
        link = CodebergWebsiteLink(website_id=website.id)
        db.add(link)

    link.base_url = data.base_url
    link.repo_owner = data.repo_owner
    link.repo_name = data.repo_name
    link.branch = data.branch

    if data.pat_override is not None:
        if data.pat_override == "":
            link.pat_override = None
        else:
            link.pat_override = encrypt_value(
                data.pat_override.strip(), app_settings.jwt_secret,
            )

    await db.flush()
    return _website_link_to_response(link)


async def delete_website_link(db: AsyncSession, slug: str) -> None:
    website = await _get_website_by_slug(db, slug)
    link = await _get_website_link(db, website.id)
    if link is None:
        return
    await db.delete(link)
    await db.flush()


def _collect_website_files(
    slug: str, site_root: Path,
) -> list[DepositFile]:
    """Walk the rendered-site tree under ``site_root`` and return a
    list of ``DepositFile`` with forge-relative POSIX paths.

    Applies safety caps (total file count + per-file bytes) so an
    accidentally-huge output never spills into the commit payload.
    """
    if not site_root.is_dir():
        raise ConflictError(
            f"Website '{slug}' has no rendered output on disk "
            f"({site_root}). Trigger a build first."
        )
    files: list[DepositFile] = []
    for path in sorted(site_root.rglob("*")):
        if not path.is_file():
            continue
        # Skip dotfiles and anything that looks like a build lock.
        rel = path.relative_to(site_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        size = path.stat().st_size
        if size > _WEBSITE_PUSH_MAX_BYTES_PER_FILE:
            raise DomainValidationError(
                "FORGE_WEBSITE_FILE_TOO_LARGE",
                f"'{rel.as_posix()}' exceeds the "
                f"{_WEBSITE_PUSH_MAX_BYTES_PER_FILE} byte cap per file.",
            )
        files.append(
            DepositFile(
                path=rel.as_posix(),
                content=path.read_bytes(),
            )
        )
        if len(files) > _WEBSITE_PUSH_MAX_FILES:
            raise DomainValidationError(
                "FORGE_WEBSITE_TOO_MANY_FILES",
                f"Rendered site exceeds the {_WEBSITE_PUSH_MAX_FILES} "
                f"file cap; trim or split the site before pushing.",
            )
    return files


async def push_website(
    db: AsyncSession,
    *,
    slug: str,
    message: str | None = None,
    site_root_override: Path | None = None,
    adapter: Any | None = None,
    transport: Any | None = None,
) -> CodebergWebsitePushResponse:
    """Push the rendered output of website ``slug`` to its linked
    Codeberg repository in a single commit.

    Requires the website to have been built (``build_status = done``)
    and its rendering mode to be STATIC or HYBRID — DYNAMIC sites
    produce nothing on disk.

    ``site_root_override`` is accepted so tests can point at a
    controlled temp directory instead of ``settings.websites_root``.
    """
    website = await _get_website_by_slug(db, slug)
    link = await _get_website_link(db, website.id)
    if link is None:
        raise NotFoundError(
            f"Website '{slug}' is not linked to a Codeberg repository.",
        )
    if website.rendering_mode == RenderingMode.DYNAMIC:
        raise ConflictError(
            "Dynamic websites are served live — there is no static "
            "output to push. Switch the site to STATIC or HYBRID "
            "rendering and build it before pushing.",
        )
    if website.build_status != BuildStatus.done:
        raise ConflictError(
            "Website has not been built successfully. Trigger a build "
            "and wait for it to finish before pushing to Codeberg.",
        )

    site_root = site_root_override or (
        Path(app_settings.websites_root) / slug
    )
    deposit_files = _collect_website_files(slug, site_root)
    if not deposit_files:
        raise ConflictError("Rendered site tree is empty — nothing to push.")

    # Token resolution (same three-way priority as the collection path).
    global_cipher = await get_decrypted_setting(db, _PAT_SETTING_KEY)
    if global_cipher:
        global_cipher = encrypt_value(global_cipher, app_settings.jwt_secret)
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
            "or a per-link override on this website.",
        )

    effective_message = (
        (message or "").strip()
        or f"Aracne2 website sync: {website.title}"
    )
    manifest = DepositManifest(
        files=deposit_files,
        branch=link.branch,
        commit_message=effective_message,
        committer_name=_COMMITTER_NAME,
        committer_email=_COMMITTER_EMAIL,
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
            "codeberg_website_push_failed", slug=slug, error=str(exc),
        )
        raise _map_forge_error(exc) from exc

    link.last_push_sha = result.sha
    link.last_push_at = result.committed_at or datetime.now(UTC)
    link.last_push_file_count = len(deposit_files)
    await db.flush()

    return CodebergWebsitePushResponse(
        sha=result.sha,
        committed_at=link.last_push_at,
        html_url=result.html_url,
        file_count=len(deposit_files),
    )
