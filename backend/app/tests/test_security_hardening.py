"""Tests for the defensive helpers shipped in the 2026-04-27 hardening commit.

Three layers:

* ``url_safety.assert_public_http_url`` — IP-literal blocklist used by
  the four forge plugins' ``base_url`` validators.
* ``uploads.read_capped`` — bounded-buffer file reader used by the
  small-cap upload routes (avatar, logo, CSS, website media).
* ``settings._sanitise_home_intro`` — bleach-based HTML allowlist for
  the public homepage cover text.
"""

from __future__ import annotations

import io
from typing import cast

import pytest
from starlette.datastructures import Headers, UploadFile

from app.core.exceptions import DomainValidationError
from app.core.url_safety import assert_public_http_url
from app.routers.settings import _sanitise_home_intro
from app.services.uploads import read_capped


# ── url_safety ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com",
        "https://codeberg.org/owner/repo",
        "http://demo.dataverse.org",
        "https://example.com:8443/api",
    ],
)
def test_assert_public_http_url_accepts_public_hostnames(url: str) -> None:
    """Public hostnames pass — the helper only catches IP literals."""
    assert_public_http_url(url)  # must not raise


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/api",
        "http://localhost/",          # ``localhost`` resolves but isn't an IP literal — out of scope
        "http://169.254.169.254/",    # AWS / GCP / Azure cloud metadata
        "http://10.0.0.1/",
        "http://172.16.0.5:5432/",
        "http://192.168.1.1/",
        "http://[::1]/",              # IPv6 loopback
        "http://[fe80::1]/",          # IPv6 link-local
        "http://[fc00::1]/",          # IPv6 unique-local
    ],
)
def test_assert_public_http_url_rejects_non_routable_ip_literals(url: str) -> None:
    """Loopback / link-local / private / multicast / reserved → ValueError.

    ``localhost`` is the lone exception in this list — it's a hostname,
    not an IP literal, so the IP-only check skips it. (DNS resolution
    is intentionally not done; see url_safety module docstring.)
    """
    if "localhost" in url:
        # documents the intentional gap — host-name lookups are out of scope
        assert_public_http_url(url)
        return
    with pytest.raises(ValueError, match="non-routable"):
        assert_public_http_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://github.com",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://",      # no host
    ],
)
def test_assert_public_http_url_rejects_bad_schemes_and_empty_hosts(url: str) -> None:
    with pytest.raises(ValueError):
        assert_public_http_url(url)


# ── read_capped ───────────────────────────────────────────────────────────────


def _upload_from_bytes(payload: bytes) -> UploadFile:
    """Build an UploadFile that wraps *payload* — Starlette's helper
    expects a SpooledTemporaryFile-like object behind the scenes."""
    buf = io.BytesIO(payload)
    return UploadFile(file=buf, filename="x.bin", headers=Headers())


@pytest.mark.asyncio
async def test_read_capped_returns_full_payload_under_cap() -> None:
    payload = b"a" * 100
    f = _upload_from_bytes(payload)
    out = await read_capped(f, max_bytes=1024)
    assert out == payload


@pytest.mark.asyncio
async def test_read_capped_aborts_before_full_buffer() -> None:
    """Once the running total exceeds max_bytes the read aborts —
    the remaining body is not buffered."""
    payload = b"x" * (5 * 1024 * 1024)  # 5 MB
    f = _upload_from_bytes(payload)
    with pytest.raises(DomainValidationError) as exc:
        await read_capped(f, max_bytes=1024 * 1024)  # 1 MB
    assert exc.value.code == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_read_capped_message_uses_kb_when_below_one_mb() -> None:
    """Sub-MB caps surface in KB so the user sees a sensible number."""
    payload = b"y" * (200 * 1024)  # 200 KB
    f = _upload_from_bytes(payload)
    with pytest.raises(DomainValidationError) as exc:
        await read_capped(f, max_bytes=64 * 1024)  # 64 KB
    assert "64 KB" in exc.value.message


# ── _sanitise_home_intro ──────────────────────────────────────────────────────


def test_sanitise_home_intro_strips_script_tag() -> None:
    """`<script>` is not in the allowlist — bleach strips it entirely."""
    out = _sanitise_home_intro("<p>hi</p><script>alert(1)</script>")
    assert "<script" not in out
    assert "<p>hi</p>" in out


def test_sanitise_home_intro_strips_inline_event_handlers() -> None:
    """`onerror` and friends fall outside the per-tag attribute allowlist."""
    out = _sanitise_home_intro('<img src="x" onerror="alert(1)" alt="hi">')
    assert "onerror" not in out
    assert 'alt="hi"' in out


def test_sanitise_home_intro_strips_javascript_uri() -> None:
    """`javascript:` href bypasses the protocol allowlist (http / https / media)."""
    out = _sanitise_home_intro('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in out


def test_sanitise_home_intro_keeps_safe_markup() -> None:
    """Allowed tags + http(s) and `media://` URIs survive untouched."""
    src = (
        '<h2>Welcome</h2>'
        '<p><strong>Bold</strong> and <em>italic</em></p>'
        '<a href="https://example.com">link</a>'
        '<img src="media://hero.jpg" alt="hero">'
    )
    out = _sanitise_home_intro(src)
    assert "<h2>" in out
    assert "<strong>" in out
    assert "<em>" in out
    assert 'href="https://example.com"' in out
    assert 'src="media://hero.jpg"' in out


def test_sanitise_home_intro_rejects_oversized_payload() -> None:
    """Anything past the 64 KB cap raises FILE_TOO_LARGE."""
    big = "a" * (65 * 1024)  # 65 KB > 64 KB cap
    with pytest.raises(DomainValidationError) as exc:
        _sanitise_home_intro(big)
    assert exc.value.code == "FILE_TOO_LARGE"


def test_sanitise_home_intro_accepts_empty_string() -> None:
    """Clearing the cover text uses an empty body — must not raise."""
    assert _sanitise_home_intro("") == ""


# silence the unused-import linter (cast is imported for forward-compat in
# _upload_from_bytes if Starlette tightens the type signature later).
_ = cast
