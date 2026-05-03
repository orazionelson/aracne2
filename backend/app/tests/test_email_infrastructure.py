"""Tests for the Phase EM-A email infrastructure (Postfix-mediated SMTP +
Jinja2 templates).

The contract:
- ``send_mail`` returns False without opening any SMTP connection when
  ``email_enabled`` is False (the safe-by-default).
- ``send_mail`` calls ``aiosmtplib.send`` exactly once when the toggle
  is on and the from-address is configured.
- ``render`` returns non-empty subject + html + text for the stub event
  in both ``en`` and ``it``.
- ``render`` falls back to the platform default language when the
  requested locale has no template directory (e.g. user with
  ``preferred_lang='fr'`` still gets a renderable email).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting
from app.services.email import render, send_mail


async def _set(
    db_session: AsyncSession, key: str, value: str, type_: str = "string"
) -> None:
    """Upsert a row in system_settings for the test."""
    existing = await db_session.get(SystemSetting, key)
    if existing is None:
        db_session.add(SystemSetting(key=key, value=value, type=type_))
    else:
        existing.value = value
    await db_session.flush()


@pytest.mark.asyncio
async def test_send_mail_noop_when_email_disabled(
    db_session: AsyncSession,
) -> None:
    """``email_enabled=false`` short-circuits before any SMTP attempt."""
    await _set(db_session, "email_enabled", "false", "bool")

    with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        result = await send_mail(
            db_session,
            to="recipient@example.org",
            subject="hi",
            html="<p>hi</p>",
            text="hi",
        )

    assert result is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_mail_calls_smtp_when_enabled(
    db_session: AsyncSession,
) -> None:
    """With the toggle on and from-address set, ``aiosmtplib.send`` runs once."""
    await _set(db_session, "email_enabled", "true", "bool")
    await _set(db_session, "email_smtp_host", "postfix")
    await _set(db_session, "email_smtp_port", "25", "int")
    await _set(db_session, "email_from_address", "noreply@example.org")
    await _set(db_session, "email_from_name", "Aracne2 Test")
    await _set(db_session, "email_subject_prefix", "[Aracne2]")

    with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        result = await send_mail(
            db_session,
            to="recipient@example.org",
            subject="hi",
            html="<p>hi</p>",
            text="hi",
        )

    assert result is True
    mock_send.assert_awaited_once()
    # Inspect the EmailMessage passed in: it must carry the prefix in subject
    # and the configured from-address.
    call_args = mock_send.await_args
    assert call_args is not None
    msg = call_args.args[0]
    assert msg["From"] == "Aracne2 Test <noreply@example.org>"
    assert msg["To"] == "recipient@example.org"
    assert "[Aracne2]" in msg["Subject"]
    assert "hi" in msg["Subject"]


@pytest.mark.asyncio
async def test_send_mail_skipped_when_from_address_empty(
    db_session: AsyncSession,
) -> None:
    """Toggle on but no from-address → still no-op + warning log; no SMTP."""
    await _set(db_session, "email_enabled", "true", "bool")
    await _set(db_session, "email_from_address", "")

    with patch("app.services.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        result = await send_mail(
            db_session,
            to="x@example.org",
            subject="hi",
            html="<p>hi</p>",
            text="hi",
        )

    assert result is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_mail_returns_false_on_smtp_failure(
    db_session: AsyncSession,
) -> None:
    """SMTP error never propagates — the caller is fire-and-forget."""
    await _set(db_session, "email_enabled", "true", "bool")
    await _set(db_session, "email_from_address", "noreply@example.org")

    with patch(
        "app.services.email.aiosmtplib.send",
        new_callable=AsyncMock,
        side_effect=ConnectionRefusedError("postfix is down"),
    ):
        result = await send_mail(
            db_session,
            to="x@example.org",
            subject="hi",
            html="<p>hi</p>",
            text="hi",
        )

    assert result is False


def test_render_stub_in_en() -> None:
    subject, html, text = render("_stub", lang="en", ctx={"name": "Alice"})
    assert subject == "Stub subject for Alice"
    assert "Hello Alice" in html
    assert "Hello Alice" in text


def test_render_stub_in_it() -> None:
    subject, html, text = render("_stub", lang="it", ctx={"name": "Mario"})
    assert subject == "Stub di prova per Mario"
    assert "Ciao Mario" in html
    assert "Ciao Mario" in text


def test_render_fallback_to_default_when_lang_missing() -> None:
    """Unknown locale falls back to the configured default language."""
    subject, _, _ = render(
        "_stub", lang="fr", default_lang="it", ctx={"name": "Pierre"}
    )
    # Italian fallback, not English — proves the default_lang is honoured.
    assert subject == "Stub di prova per Pierre"


def test_render_fallback_to_en_when_default_also_missing() -> None:
    """Unknown locale + unknown default still resolves to English."""
    subject, _, _ = render(
        "_stub", lang="fr", default_lang="de", ctx={"name": "Hans"}
    )
    assert subject == "Stub subject for Hans"


def test_render_html_autoescapes_user_input() -> None:
    """HTML body must autoescape — otherwise ctx values become an XSS vector."""
    _, html, text = render("_stub", lang="en", ctx={"name": "<script>x</script>"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # Plain text body does NOT autoescape — that's correct.
    assert "<script>" in text


def test_render_unknown_event_raises() -> None:
    import pytest as _pytest

    with _pytest.raises(FileNotFoundError):
        render("does_not_exist_event", lang="en", ctx={})
