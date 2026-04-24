"""Codeberg plugin — website push service tests.

Uses a ``tmp_path`` to stand in for ``settings.websites_root`` so we
can control the exact set of files the service sees on disk. The
adapter is mocked so no HTTP is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from app.models.system_setting import SystemSetting
from app.models.website import BuildStatus, RenderingMode, Website
from app.plugins._lib.git_forge.models import CommitResult, InitializeBundle
from app.plugins.codeberg_integration import service
from app.plugins.codeberg_integration.schemas import (
    CodebergWebsiteLinkCreate,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


async def _mk_website(
    db: AsyncSession,
    *,
    slug: str = "my-site",
    rendering_mode: RenderingMode = RenderingMode.STATIC,
    build_status: BuildStatus = BuildStatus.done,
) -> Website:
    row = Website(
        slug=slug,
        title="My Site",
        rendering_mode=rendering_mode,
        build_status=build_status,
    )
    db.add(row)
    await db.flush()
    return row


async def _mk_setting(
    db: AsyncSession, key: str, value: str = "",
) -> None:
    db.add(SystemSetting(key=key, value=value, type="string"))
    await db.flush()


def _write_site(root: Path) -> None:
    """Lay out a small rendered-site tree under ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_bytes(b"<html><body>Home</body></html>")
    (root / "browse.html").write_bytes(b"<html><body>Browse</body></html>")
    css = root / "css"
    css.mkdir(exist_ok=True)
    (css / "theme.css").write_bytes(b"body{font-family:serif}")
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "one.html").write_bytes(b"<html>1</html>")
    # A dotfile that the service must skip.
    (root / ".DS_Store").write_bytes(b"junk")


@dataclass
class _RecordingAdapter:
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

    async def initialize_bundle(self, **_: Any) -> InitializeBundle:
        raise NotImplementedError


# ── Push: happy path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_push_website_collects_files_and_records_commit(
    db_session: AsyncSession, tmp_path: Path,
) -> None:
    website = await _mk_website(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_website_link(
        db_session, website.slug,
        CodebergWebsiteLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="site",
            pat_override="PAT",
        ),
    )
    site_root = tmp_path / website.slug
    _write_site(site_root)

    adapter = _RecordingAdapter(
        result=CommitResult(
            sha="site-sha", committed_at=datetime.now(UTC),
            html_url="https://codeberg.org/alice/site/commit/site-sha",
        ),
    )
    resp = await service.push_website(
        db_session, slug=website.slug,
        site_root_override=site_root, adapter=adapter,
    )
    # The .DS_Store dotfile must be skipped.
    assert resp.file_count == 4
    manifest = adapter.last_call["manifest"]
    paths = sorted(f.path for f in manifest.files)
    assert paths == [
        "browse.html", "css/theme.css", "docs/one.html", "index.html",
    ]
    # Paths are POSIX even on non-Linux filesystems.
    assert all("\\" not in p for p in paths)


# ── Push: refuses DYNAMIC and not-yet-built sites ────────────────────────


@pytest.mark.asyncio
async def test_push_website_refuses_dynamic_mode(
    db_session: AsyncSession, tmp_path: Path,
) -> None:
    website = await _mk_website(
        db_session, rendering_mode=RenderingMode.DYNAMIC,
    )
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_website_link(
        db_session, website.slug,
        CodebergWebsiteLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="site",
            pat_override="PAT",
        ),
    )
    with pytest.raises(ConflictError):
        await service.push_website(
            db_session, slug=website.slug,
            site_root_override=tmp_path / website.slug,
        )


@pytest.mark.asyncio
async def test_push_website_refuses_when_not_built(
    db_session: AsyncSession, tmp_path: Path,
) -> None:
    website = await _mk_website(
        db_session, build_status=BuildStatus.idle,
    )
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_website_link(
        db_session, website.slug,
        CodebergWebsiteLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="site",
            pat_override="PAT",
        ),
    )
    with pytest.raises(ConflictError):
        await service.push_website(
            db_session, slug=website.slug,
            site_root_override=tmp_path / website.slug,
        )


@pytest.mark.asyncio
async def test_push_website_refuses_when_build_dir_missing(
    db_session: AsyncSession, tmp_path: Path,
) -> None:
    website = await _mk_website(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    await service.upsert_website_link(
        db_session, website.slug,
        CodebergWebsiteLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="site",
            pat_override="PAT",
        ),
    )
    # No directory on disk → collector refuses.
    with pytest.raises(ConflictError):
        await service.push_website(
            db_session, slug=website.slug,
            site_root_override=tmp_path / "missing",
        )


@pytest.mark.asyncio
async def test_push_website_missing_link_is_404(
    db_session: AsyncSession, tmp_path: Path,
) -> None:
    website = await _mk_website(db_session)
    with pytest.raises(NotFoundError):
        await service.push_website(
            db_session, slug=website.slug,
            site_root_override=tmp_path / website.slug,
        )


@pytest.mark.asyncio
async def test_push_website_pat_missing_error(
    db_session: AsyncSession, tmp_path: Path,
) -> None:
    website = await _mk_website(db_session)
    await _mk_setting(db_session, "codeberg_integration_pat", "")
    # Link has no per-link override, global is empty.
    await service.upsert_website_link(
        db_session, website.slug,
        CodebergWebsiteLinkCreate(
            base_url="https://codeberg.org",
            repo_owner="alice", repo_name="site",
        ),
    )
    site_root = tmp_path / website.slug
    _write_site(site_root)
    with pytest.raises(DomainValidationError) as exc:
        await service.push_website(
            db_session, slug=website.slug,
            site_root_override=site_root,
        )
    assert exc.value.code == "FORGE_PAT_MISSING"


# ── Link CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_website_link_crud_roundtrip(
    db_session: AsyncSession,
) -> None:
    website = await _mk_website(db_session)
    resp = await service.upsert_website_link(
        db_session, website.slug,
        CodebergWebsiteLinkCreate(
            base_url="https://git.example.edu",  # self-hosted Forgejo
            repo_owner="alice", repo_name="site", branch="trunk",
            pat_override="PAT",
        ),
    )
    assert resp.base_url == "https://git.example.edu"
    assert resp.branch == "trunk"
    assert resp.pat_override_set is True
    assert resp.html_url == "https://git.example.edu/alice/site"

    # Idempotent: calling delete twice is fine.
    await service.delete_website_link(db_session, website.slug)
    await service.delete_website_link(db_session, website.slug)
