"""Codeberg plugin — service-layer tests.

No HTTP at all — the service is invoked directly with a mocked
ExistDBClient and a mocked adapter so we exercise token resolution,
manifest construction, link bookkeeping, and error translation
without touching the network or the real forge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.encryption import encrypt_value
from app.core.exceptions import DomainValidationError, NotFoundError
from app.models.collection import Collection, CollectionStatus
from app.models.system_setting import SystemSetting
from app.plugins._lib.git_forge.errors import AuthFailed, RepoNotFound
from app.plugins._lib.git_forge.models import CommitResult
from app.plugins.codeberg_integration import service
from app.plugins.codeberg_integration.models import CodebergCollectionLink
from app.plugins.codeberg_integration.schemas import CodebergLinkCreate


# ── Helpers ────────────────────────────────────────────────────────────────


async def _mk_collection(
    db: AsyncSession, slug: str = "magna-cartha",
) -> Collection:
    col = Collection(
        slug=slug, title="Magna Cartha",
        description="Test edition",
        status=CollectionStatus.draft,
        is_public=False,
    )
    db.add(col)
    await db.flush()
    return col


async def _mk_setting(
    db: AsyncSession, key: str, value: str = "",
) -> None:
    row = SystemSetting(key=key, value=value, type="string")
    db.add(row)
    await db.flush()


def _mock_existdb(files: dict[str, bytes]) -> AsyncMock:
    existdb = AsyncMock()
    existdb.list_collection.return_value = list(files.keys())
    existdb.get_document.side_effect = lambda _slug, filename: files[filename]
    return existdb


@dataclass
class _RecordingAdapter:
    """Stand-in adapter that records the manifest instead of hitting a forge."""

    forge_id: str = "codeberg"
    result: CommitResult | None = None
    raise_: Exception | None = None

    async def push_manifest(self, **kwargs: Any) -> CommitResult:
        self.last_call = kwargs
        if self.raise_ is not None:
            raise self.raise_
        assert self.result is not None
        return self.result

    async def get_head_sha(self, **_: Any) -> str | None:
        return None

    async def initialize_bundle(self, **_: Any) -> Any:
        raise NotImplementedError


# ── Link CRUD ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_link_creates_new_row_and_encrypts_override(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    data = CodebergLinkCreate(
        base_url="https://codeberg.org",
        repo_owner="alice",
        repo_name="edition",
        branch="main",
        pat_override="PER_COLLECTION_PAT",
    )
    resp = await service.upsert_link(db_session, col.slug, data)
    assert resp.pat_override_set is True

    row = await db_session.scalar(
        select(CodebergCollectionLink).where(
            CodebergCollectionLink.collection_id == col.id,
        )
    )
    assert row is not None
    assert row.pat_override is not None
    assert row.pat_override != "PER_COLLECTION_PAT"  # encrypted


@pytest.mark.asyncio
async def test_upsert_link_none_pat_override_leaves_existing_alone(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    # First upsert sets a PAT override.
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="FIRST_PAT",
        ),
    )
    # Second upsert omits pat_override (None) → existing value untouched.
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition-renamed",
            pat_override=None,
        ),
    )
    link = await service._get_link(db_session, col.id)  # type: ignore[attr-defined]
    assert link is not None
    assert link.repo_name == "edition-renamed"
    assert link.pat_override is not None


@pytest.mark.asyncio
async def test_upsert_link_empty_string_clears_override(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="PAT",
        ),
    )
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="",
        ),
    )
    link = await service._get_link(db_session, col.id)  # type: ignore[attr-defined]
    assert link is not None
    assert link.pat_override is None


@pytest.mark.asyncio
async def test_delete_link_is_idempotent(db_session: AsyncSession) -> None:
    col = await _mk_collection(db_session)
    # No link yet → no error.
    await service.delete_link(db_session, col.slug)
    # Create one and delete.
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
        ),
    )
    await service.delete_link(db_session, col.slug)
    assert await service._get_link(db_session, col.id) is None  # type: ignore[attr-defined]


# ── Push: token resolution ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_uses_link_override_when_set(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    # Global PAT seeded empty.
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="OVERRIDE_PAT",
        ),
    )
    adapter = _RecordingAdapter(
        result=CommitResult(sha="abc", committed_at=__import__("datetime").datetime.now(__import__("datetime").UTC)),
    )
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    resp = await service.push_collection(
        db_session, existdb, slug=col.slug, adapter=adapter,
    )
    assert resp.sha == "abc"
    assert adapter.last_call["token"] == "OVERRIDE_PAT"


@pytest.mark.asyncio
async def test_push_falls_back_to_global_pat_when_no_override(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    encrypted = encrypt_value("GLOBAL_PAT", app_settings.jwt_secret)
    await _mk_setting(db_session, "codeberg_integration_pat", encrypted)
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override=None,
        ),
    )
    adapter = _RecordingAdapter(
        result=CommitResult(sha="abc", committed_at=__import__("datetime").datetime.now(__import__("datetime").UTC)),
    )
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    await service.push_collection(
        db_session, existdb, slug=col.slug, adapter=adapter,
    )
    assert adapter.last_call["token"] == "GLOBAL_PAT"


@pytest.mark.asyncio
async def test_push_raises_pat_missing_when_both_scopes_empty(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
        ),
    )
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    with pytest.raises(DomainValidationError) as exc:
        await service.push_collection(db_session, existdb, slug=col.slug)
    assert exc.value.code == "FORGE_PAT_MISSING"


# ── Push: manifest shape ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_builds_manifest_with_documents_prefix(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            branch="trunk",
            pat_override="PAT",
        ),
    )
    adapter = _RecordingAdapter(
        result=CommitResult(sha="sha1", committed_at=__import__("datetime").datetime.now(__import__("datetime").UTC)),
    )
    existdb = _mock_existdb({"doc1.xml": b"<d1/>", "doc2.xml": b"<d2/>"})
    await service.push_collection(
        db_session, existdb,
        slug=col.slug, message="Custom message", adapter=adapter,
    )
    manifest = adapter.last_call["manifest"]
    assert manifest.branch == "trunk"
    assert manifest.commit_message == "Custom message"
    assert [f.path for f in manifest.files] == [
        "documents/doc1.xml", "documents/doc2.xml",
    ]
    assert manifest.files[0].content == b"<d1/>"


@pytest.mark.asyncio
async def test_push_empty_collection_raises_conflict(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="PAT",
        ),
    )
    existdb = _mock_existdb({})
    with pytest.raises(Exception):  # ConflictError is subclass of DomainException
        await service.push_collection(db_session, existdb, slug=col.slug)


# ── Push: error mapping ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_auth_failed_surfaces_as_domain_error(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="BAD_PAT",
        ),
    )
    adapter = _RecordingAdapter(raise_=AuthFailed("nope"))
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    with pytest.raises(DomainValidationError) as exc:
        await service.push_collection(
            db_session, existdb, slug=col.slug, adapter=adapter,
        )
    assert exc.value.code == "FORGE_AUTH_FAILED"


@pytest.mark.asyncio
async def test_push_repo_not_found_surfaces_as_domain_error(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="missing",
            pat_override="PAT",
        ),
    )
    adapter = _RecordingAdapter(raise_=RepoNotFound("404"))
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    with pytest.raises(DomainValidationError) as exc:
        await service.push_collection(
            db_session, existdb, slug=col.slug, adapter=adapter,
        )
    assert exc.value.code == "FORGE_REPO_NOT_FOUND"


# ── Bookkeeping ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_success_updates_last_push_columns(
    db_session: AsyncSession,
) -> None:
    col = await _mk_collection(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_link(
        db_session, col.slug,
        CodebergLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="edition",
            pat_override="PAT",
        ),
    )
    adapter = _RecordingAdapter(
        result=CommitResult(
            sha="fresh-sha",
            committed_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            html_url="https://codeberg.org/alice/edition/commit/fresh-sha",
        ),
    )
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    resp = await service.push_collection(
        db_session, existdb, slug=col.slug, adapter=adapter,
    )
    assert resp.sha == "fresh-sha"
    assert resp.file_count == 1

    link = await service._get_link(db_session, col.id)  # type: ignore[attr-defined]
    assert link is not None
    assert link.last_push_sha == "fresh-sha"
    assert link.last_push_at is not None


@pytest.mark.asyncio
async def test_push_missing_link_is_404(db_session: AsyncSession) -> None:
    col = await _mk_collection(db_session)
    existdb = _mock_existdb({"a.xml": b"<a/>"})
    with pytest.raises(NotFoundError):
        await service.push_collection(db_session, existdb, slug=col.slug)
