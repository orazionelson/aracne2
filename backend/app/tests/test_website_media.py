"""Unit tests for the per-website media service.

Scope: filesystem-only helpers. The HTTP layer + builder integration
(covered elsewhere) rely on these primitives, so if they regress the
whole feature falls apart. Targets:

* ``sanitize_filename`` — extension allow-list, path traversal,
  Unicode folding, length cap, leading-dot rejection.
* ``save_media`` / ``list_media`` / ``delete_media`` / ``read_media``
  round-trip on a temp media root.
* ``_sanitize_svg`` — scripts, event handlers and javascript: refs
  are scrubbed.
* ``rewrite_media_refs`` — DYNAMIC returns API URLs, STATIC returns
  relative paths and reports the referenced filename set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import DomainValidationError, NotFoundError
from app.services import website_media as wm


@pytest.fixture(autouse=True)
def _redirect_media_root(tmp_path, monkeypatch):
    """Point ``settings.media_dir`` at a fresh temp dir for every test."""
    from app.config import settings

    monkeypatch.setattr(settings, "media_dir", tmp_path)
    yield


# ── sanitize_filename ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "given,expected",
    [
        ("logo.png", "logo.png"),
        ("My Logo.PNG", "my-logo.png"),
        ("École.jpg", "ecole.jpg"),  # accents folded
        ("photo_1.WEBP", "photo_1.webp"),
        ("../../../etc/passwd.png", "passwd.png"),  # traversal stripped
        ("cover image.jpeg", "cover-image.jpeg"),
        ("multi---dash.png", "multi-dash.png"),
    ],
)
def test_sanitize_filename_normalises(given: str, expected: str) -> None:
    assert wm.sanitize_filename(given) == expected


@pytest.mark.parametrize(
    "given",
    [
        "",
        ".hidden.png",  # leading-dot rejection
        "doc.pdf",  # extension not in allow-list
        "script.js",
        "no-extension",
        "x" * 200 + ".png",  # length cap
        # NFKD+ASCII fold collapses Han / Cyrillic / Devanagari / etc.
        # to nothing; the basename then becomes bare ".png" → rejected.
        "中文.png",
    ],
)
def test_sanitize_filename_rejects(given: str) -> None:
    with pytest.raises(DomainValidationError):
        wm.sanitize_filename(given)


# ── CRUD roundtrip ───────────────────────────────────────────────────────────


def test_save_list_read_delete_roundtrip() -> None:
    slug = "my-site"
    png = b"\x89PNG\r\n\x1a\nDUMMY"
    saved = wm.save_media(slug, "Hero.PNG", png)
    assert saved.filename == "hero.png"
    assert saved.content_type == "image/png"

    files = wm.list_media(slug)
    assert [f.filename for f in files] == ["hero.png"]

    payload, ctype = wm.read_media(slug, "hero.png")
    assert payload == png
    assert ctype == "image/png"

    wm.delete_media(slug, "hero.png")
    assert wm.list_media(slug) == []


def test_save_rejects_oversize() -> None:
    big = b"\x00" * (wm._MAX_UPLOAD_BYTES + 1)  # just over the cap
    with pytest.raises(DomainValidationError):
        wm.save_media("site-a", "big.png", big)


def test_delete_missing_raises_404() -> None:
    with pytest.raises(NotFoundError):
        wm.delete_media("site-a", "nothing.png")


def test_read_missing_raises_404() -> None:
    with pytest.raises(NotFoundError):
        wm.read_media("site-a", "nothing.png")


# ── SVG sanitisation ─────────────────────────────────────────────────────────


def test_svg_scripts_are_stripped() -> None:
    dirty = (
        b'<?xml version="1.0"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        b'<script>alert("xss")</script>'
        b'<circle cx="50" cy="50" r="40" onclick="steal()"/>'
        b'<a href="javascript:alert(1)">click</a>'
        b"</svg>"
    )
    wm.save_media("site-a", "icon.svg", dirty)
    payload, _ = wm.read_media("site-a", "icon.svg")
    text = payload.decode()
    # Scripting removed
    assert "<script" not in text.lower()
    assert "onload" not in text.lower()
    assert "onclick" not in text.lower()
    assert "javascript:" not in text.lower()
    # Drawing preserved
    assert "<circle" in text or "circle" in text


def test_svg_invalid_markup_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        wm.save_media("site-a", "broken.svg", b"not <xml at all")


# ── URL rewriter ─────────────────────────────────────────────────────────────


def test_rewrite_dynamic_mode_emits_api_urls() -> None:
    html = '<img src="media://logo.png"> and <a href="media://file.jpg">x</a>'
    out = wm.rewrite_media_refs(html, "my-site", mode="dynamic")
    assert 'src="/api/v1/websites/my-site/media/logo.png"' in out
    assert 'href="/api/v1/websites/my-site/media/file.jpg"' in out


def test_rewrite_static_mode_emits_relative_paths_and_collects() -> None:
    html = (
        '<img src="media://cover.webp">'
        '<div>See media://illustration.png inside text.</div>'
    )
    collected: set[str] = set()
    out = wm.rewrite_media_refs(html, "s", mode="static", collected=collected)
    assert 'src="media/cover.webp"' in out
    assert "media/illustration.png" in out
    assert collected == {"cover.webp", "illustration.png"}


def test_rewrite_static_mode_honours_custom_prefix() -> None:
    """Subdirectory pages (``pages/…``, ``docs/…``) need ``../media/``."""
    html = '<img src="media://logo.png">'
    out = wm.rewrite_media_refs(html, "s", mode="static", static_prefix="../media/")
    assert 'src="../media/logo.png"' in out


def test_rewrite_no_match_returns_unchanged() -> None:
    html = "<p>No media here.</p>"
    assert wm.rewrite_media_refs(html, "s", mode="dynamic") == html


def test_rewrite_ignores_traversal_attempts() -> None:
    """A hand-edited ``media://../etc/passwd`` is not caught by the strict
    regex — the ``/`` breaks the filename pattern, so nothing rewrites."""
    html = '<img src="media://../etc/passwd">'
    out = wm.rewrite_media_refs(html, "s", mode="dynamic")
    # Left verbatim (broken image) — safer than generating a valid API URL.
    assert out == html


# ── copy_referenced_media_to_build ───────────────────────────────────────────


def test_copy_selectively_copies_referenced_files(tmp_path: Path) -> None:
    slug = "siteX"
    wm.save_media(slug, "a.png", b"A")
    wm.save_media(slug, "b.png", b"B")
    wm.save_media(slug, "c.png", b"C")

    site_dir = tmp_path / "build" / slug
    site_dir.mkdir(parents=True)

    # Only ``a.png`` is referenced — ``c.png`` should NOT be copied.
    wm.copy_referenced_media_to_build(slug, site_dir, {"a.png", "b.png"})

    out_dir = site_dir / "media"
    assert (out_dir / "a.png").read_bytes() == b"A"
    assert (out_dir / "b.png").read_bytes() == b"B"
    assert not (out_dir / "c.png").exists()


def test_copy_handles_missing_reference_gracefully(tmp_path: Path) -> None:
    """Referencing a file that was deleted between render and copy must
    not crash the build — the page simply renders a broken image."""
    slug = "siteY"
    wm.save_media(slug, "present.png", b"X")
    site_dir = tmp_path / "build" / slug
    site_dir.mkdir(parents=True)

    wm.copy_referenced_media_to_build(
        slug, site_dir, {"present.png", "missing.png"}
    )
    assert (site_dir / "media" / "present.png").exists()
    assert not (site_dir / "media" / "missing.png").exists()
