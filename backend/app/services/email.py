"""Email channel — Postfix-mediated SMTP + Jinja2 templates.

Phase EM-A of the email channels feature. The app talks to a local Postfix
container on the docker network (no auth, no TLS); Postfix handles the
queue, retry, DKIM signing and the relay to the operator's smarthost.
Aracne2 is therefore vendor-neutral and stores no SMTP secrets in the DB.

Public API:

- :func:`send_mail` — async, fire-and-forget-friendly. Returns ``False`` on
  any failure (logged) and ``True`` on success. Never raises.
- :func:`render` — sync, loads ``app/email_templates/{event}/{lang}/`` via
  Jinja2 and returns ``(subject, html_body, text_body)``. Falls back to the
  platform's ``default_language`` setting when the requested locale has no
  template directory.
- :func:`is_email_enabled` — async, reads the ``email_enabled``
  system_setting; ``send_mail`` returns False when this is ``"false"``.

Failures are logged through structlog with the same structured-record
pattern used by the rest of the platform; recipient addresses are never
emitted in the log payload to respect the privacy rule from CLAUDE.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import aiosmtplib
import structlog
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()

_TEMPLATES_DIR = Path(__file__).parent.parent / "email_templates"

# Jinja2 environment with autoescape on for HTML; .txt and subject.txt
# render literally. ``select_autoescape`` keys on file extension.
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=False),
    keep_trailing_newline=True,
)


def _hash_recipient(addr: str) -> str:
    """Pseudonymise a recipient address for log records.

    The recipient is hashed (no salt — log correlation across requests is
    a feature) so an operator inspecting logs can match a complaint to a
    specific outgoing email without seeing the address itself.
    """
    return "sha256:" + hashlib.sha256(addr.encode("utf-8")).hexdigest()[:16]


async def is_email_enabled(db: AsyncSession) -> bool:
    """Return True when the operator has opted in via ``email_enabled``.

    Default is ``"false"`` (see ``db/seed.py``) so a fresh install never
    spams a relay accidentally; the operator must flip the toggle through
    the Admin Settings UI before the first email goes out.
    """
    return (await get_decrypted_setting(db, "email_enabled")) == "true"


async def _read_smtp_config(db: AsyncSession) -> dict[str, Any]:
    """Pull the Postfix-mediated SMTP knobs out of system_settings.

    All values are stored as strings; numerics are coerced here. Empty
    ``email_from_address`` is treated as a misconfiguration — the caller
    bails out before opening a connection.
    """
    host = (await get_decrypted_setting(db, "email_smtp_host")) or "postfix"
    port_raw = (await get_decrypted_setting(db, "email_smtp_port")) or "25"
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 25
    return {
        "host": host,
        "port": port,
        "from_address": (await get_decrypted_setting(db, "email_from_address")) or "",
        "from_name": (await get_decrypted_setting(db, "email_from_name")) or "Aracne2",
        "subject_prefix": (await get_decrypted_setting(db, "email_subject_prefix"))
        or "[Aracne2]",
    }


async def send_mail(
    db: AsyncSession,
    *,
    to: str,
    subject: str,
    html: str,
    text: str,
) -> bool:
    """Send an email through the local Postfix container.

    Returns ``True`` on success, ``False`` on every failure mode
    (disabled / misconfigured / SMTP error). Never raises — the caller
    is typically a fire-and-forget background task that must not surface
    SMTP errors back to the originating workflow operation.

    The recipient address is never written to logs in plaintext; only a
    short SHA-256 prefix is recorded so an operator can correlate
    failures with specific outgoing messages.
    """
    if not await is_email_enabled(db):
        logger.info("email_send_skipped", reason="email_enabled=false")
        return False

    cfg = await _read_smtp_config(db)
    if not cfg["from_address"]:
        logger.warning("email_send_skipped", reason="email_from_address is empty")
        return False

    full_subject = f"{cfg['subject_prefix']} {subject}".strip()

    msg = EmailMessage()
    msg["From"] = f"{cfg['from_name']} <{cfg['from_address']}>"
    msg["To"] = to
    msg["Subject"] = full_subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=cfg["port"],
            start_tls=False,
            use_tls=False,
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001 — fire-and-forget contract
        logger.error(
            "email_send_failed",
            recipient=_hash_recipient(to),
            host=cfg["host"],
            port=cfg["port"],
            error=str(exc),
        )
        return False

    logger.info(
        "email_send_ok",
        recipient=_hash_recipient(to),
        subject_prefix=cfg["subject_prefix"],
    )
    return True


# ── Templating ────────────────────────────────────────────────────────────────

# Languages we ship templates for. When the user's preferred_lang is not
# in this set the fallback is the platform's default_language setting,
# computed at render time via _resolve_lang.
_SUPPORTED_LANGS: tuple[str, ...] = ("en", "it")


def _template_dir_exists(event: str, lang: str) -> bool:
    return (_TEMPLATES_DIR / event / lang).is_dir()


def _resolve_lang(event: str, requested: str | None, default: str) -> str:
    """Pick the closest available locale for *event*.

    Preference order: requested → default (system_setting) → 'en' →
    first supported. Each candidate must have a ``{event}/{lang}/``
    directory; we never silently fall back to a missing one.
    """
    candidates = [requested, default, "en", *_SUPPORTED_LANGS]
    for lang in candidates:
        if lang and _template_dir_exists(event, lang):
            return lang
    raise FileNotFoundError(f"No template directory for event '{event}' in any language")


def render(
    event: str,
    *,
    lang: str,
    default_lang: str = "en",
    ctx: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """Render the three template files for *event* in *lang*.

    Each event directory must contain ``subject.txt``, ``body.html`` and
    ``body.txt``; subjects render with autoescape OFF (no HTML in
    headers), the HTML body with autoescape ON, the plaintext body with
    autoescape OFF.

    Raises FileNotFoundError if no localised template exists at all.
    """
    chosen = _resolve_lang(event, lang, default_lang)
    ctx = ctx or {}
    subject = _jinja_env.get_template(f"{event}/{chosen}/subject.txt").render(**ctx).strip()
    html_body = _jinja_env.get_template(f"{event}/{chosen}/body.html").render(**ctx)
    text_body = _jinja_env.get_template(f"{event}/{chosen}/body.txt").render(**ctx)
    return subject, html_body, text_body
