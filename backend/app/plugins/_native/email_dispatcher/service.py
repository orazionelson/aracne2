"""Email dispatcher service — Phase EM-B of the email channels feature.

Translates collection workflow hook events into outgoing emails. Each
handler is fire-and-forget: a background task opens its own
``AsyncSessionLocal`` so the calling transaction commits independently,
catches every exception, and never propagates back to the workflow
operation that triggered the hook.

Recipients are filtered:
- workflow emails respect ``user.email_notifications_enabled`` (default
  ``True``); a user who unticks the toggle on their profile stops
  receiving workflow emails entirely
- the actor of the event is always excluded — an EiC who clicks
  "Publish" doesn't email themselves

The platform-wide ``email_enabled`` system_setting still gates the SMTP
side: when False, ``send_mail`` is a silent no-op and the dispatcher
runs through to completion logging zero sends.
"""

from __future__ import annotations

import asyncio
from typing import cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import AsyncSessionLocal
from app.models.collection import Collection
from app.models.role import Role, RoleName, UserRole
from app.models.user import User
from app.services.email import render, send_mail
from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()


# Hook events the dispatcher reacts to.
_TEMPLATES = {
    "collection.submitted": "collection_submitted",
    "collection.rejected": "collection_rejected",
    "collection.published": "collection_published",
}


def _site_collection_url(slug: str) -> str:
    """Build a deep link the email recipient can click.

    Falls back to a relative path when ``public_base_url`` is unset; the
    email body still renders, the link just isn't fully qualified.
    Operators who care about clickable email links set the setting from
    the Admin Settings UI.
    """
    return f"/collections/{slug}"


async def _resolve_default_lang(db: AsyncSession) -> str:
    return (await get_decrypted_setting(db, "default_language")) or "en"


async def _resolve_public_base_url(db: AsyncSession) -> str:
    return (await get_decrypted_setting(db, "public_base_url")) or ""


async def _fetch_active_eics(
    db: AsyncSession, exclude_user_id
) -> list[User]:
    """Return every active EiC+ user with email notifications on.

    Same query shape as ``_notify_broadcast_eic`` in services/xmldb.py.
    """
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            Role.name.in_([RoleName.EditorInChief, RoleName.Admin]),
            UserRole.revoked_at.is_(None),
            User.is_active.is_(True),
            User.email_notifications_enabled.is_(True),
            User.id != exclude_user_id,
        )
        .distinct()
    )
    return list(await db.scalars(stmt))


async def _send_one(
    db: AsyncSession,
    recipient: User,
    template_event: str,
    base_ctx: dict[str, object],
    default_lang: str,
) -> None:
    lang = (recipient.preferred_lang or default_lang).split("-")[0]
    ctx = dict(base_ctx)
    ctx["recipient_display_name"] = recipient.display_name or recipient.username
    try:
        subject, html, text = render(
            template_event, lang=lang, default_lang=default_lang, ctx=ctx
        )
    except FileNotFoundError as exc:
        logger.error(
            "email_template_missing",
            event=template_event,
            error=str(exc),
        )
        return
    await send_mail(db, to=recipient.email, subject=subject, html=html, text=text)


async def _dispatch_collection_event(
    template_event: str,
    *,
    collection_id,
    actor_id,
    actor_display: str,
    note: str | None,
) -> None:
    """Background task body — runs detached from the calling transaction.

    Opens its own session because the workflow service has already
    committed (or will commit) by the time this task runs; reusing the
    caller's session would race with that commit.
    """
    async with AsyncSessionLocal() as db:
        try:
            collection = await db.get(Collection, collection_id)
            if collection is None:
                logger.info(
                    "email_dispatch_collection_missing",
                    template_event=template_event,
                    collection_id=str(collection_id),
                )
                return

            default_lang = await _resolve_default_lang(db)
            base_url = await _resolve_public_base_url(db)
            collection_url = (
                f"{base_url.rstrip('/')}{_site_collection_url(collection.slug)}"
                if base_url
                else _site_collection_url(collection.slug)
            )
            base_ctx: dict[str, object] = {
                "actor_name": actor_display,
                "collection_title": collection.title,
                "collection_slug": collection.slug,
                "collection_url": collection_url,
                "note": (note or "").strip(),
            }

            # Resolve the recipient set per event.
            recipients: list[User] = []
            if template_event == "collection_submitted":
                recipients = await _fetch_active_eics(db, exclude_user_id=actor_id)
            else:
                # Both "rejected" and "published" go to the assigned editor.
                if collection.editor_id is not None:
                    editor = await db.get(User, collection.editor_id)
                    if (
                        editor is not None
                        and editor.is_active
                        and editor.email_notifications_enabled
                        and editor.id != actor_id
                    ):
                        recipients = [editor]

            if not recipients:
                logger.info(
                    "email_dispatch_no_recipients",
                    template_event=template_event,
                    slug=collection.slug,
                )
                return

            for recipient in recipients:
                await _send_one(
                    db, recipient, template_event, base_ctx, default_lang
                )
        except Exception as exc:  # noqa: BLE001 — fire-and-forget contract
            logger.error(
                "email_dispatch_failed",
                template_event=template_event,
                error=str(exc),
            )


def _actor_label(actor: User) -> str:
    return actor.display_name or actor.username


def _schedule(template_event: str, **kwargs: object) -> None:
    """Spawn the dispatch task without awaiting it.

    Named so the ``asyncio`` debugger / structlog records can identify
    which template a stray task belongs to.
    """
    asyncio.create_task(
        _dispatch_collection_event(template_event, **kwargs),  # type: ignore[arg-type]
        name=f"email-{template_event}",
    )


# ── Hook handler entry points (registered by plugin.py) ──────────────────────


async def on_collection_submitted(**kwargs: object) -> None:
    collection = cast(Collection | None, kwargs.get("collection"))
    actor = cast(User | None, kwargs.get("actor"))
    if collection is None or actor is None:
        return
    _schedule(
        "collection_submitted",
        collection_id=collection.id,
        actor_id=actor.id,
        actor_display=_actor_label(actor),
        note=cast(str | None, kwargs.get("note")),
    )


async def on_collection_rejected(**kwargs: object) -> None:
    collection = cast(Collection | None, kwargs.get("collection"))
    actor = cast(User | None, kwargs.get("actor"))
    if collection is None or actor is None:
        return
    _schedule(
        "collection_rejected",
        collection_id=collection.id,
        actor_id=actor.id,
        actor_display=_actor_label(actor),
        note=cast(str | None, kwargs.get("note")),
    )


async def on_collection_published(**kwargs: object) -> None:
    collection = cast(Collection | None, kwargs.get("collection"))
    actor = cast(User | None, kwargs.get("actor"))
    if collection is None or actor is None:
        return
    _schedule(
        "collection_published",
        collection_id=collection.id,
        actor_id=actor.id,
        actor_display=_actor_label(actor),
        note=cast(str | None, kwargs.get("note")),
    )


# ── GDPR request notification ─────────────────────────────────────────────────


async def _fetch_active_admins(db: AsyncSession) -> list[User]:
    """Return every active Admin with email notifications enabled.

    The `email_notifications_enabled` toggle is what users use to opt
    out of *workflow* emails; we honour it for GDPR notifications too
    so an Admin who disabled the workflow stream stays consistent.
    Operators that want a separate GDPR-only pager wire it themselves.
    """
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            Role.name == RoleName.Admin,
            UserRole.revoked_at.is_(None),
            User.is_active.is_(True),
            User.email_notifications_enabled.is_(True),
        )
        .distinct()
    )
    return list(await db.scalars(stmt))


async def _dispatch_gdpr_request(
    *,
    requester_id,
    requester_username: str,
    reason: str | None,
) -> None:
    """Send the GDPR-request email to every active Admin.

    Background task; opens its own AsyncSessionLocal so the
    triggering request's transaction can commit independently.
    Errors are caught and logged — the queue row in
    ``gdpr_requests`` is the canonical accountability surface.
    """
    async with AsyncSessionLocal() as db:
        try:
            default_lang = await _resolve_default_lang(db)
            base_url = await _resolve_public_base_url(db)
            admin_queue_url = (
                f"{base_url.rstrip('/')}/admin/gdpr"
                if base_url
                else "/admin/gdpr"
            )
            base_ctx: dict[str, object] = {
                "requester_username": requester_username,
                "reason": (reason or "").strip(),
                "admin_queue_url": admin_queue_url,
            }
            recipients = await _fetch_active_admins(db)
            if not recipients:
                logger.info(
                    "email_dispatch_no_recipients",
                    template_event="gdpr_request_submitted",
                    requester=requester_username,
                )
                return
            for recipient in recipients:
                await _send_one(
                    db,
                    recipient,
                    "gdpr_request_submitted",
                    base_ctx,
                    default_lang,
                )
        except Exception as exc:  # noqa: BLE001 — fire-and-forget contract
            logger.error(
                "email_dispatch_failed",
                template_event="gdpr_request_submitted",
                error=str(exc),
            )


async def on_gdpr_request_submitted(**kwargs: object) -> None:
    """Hook handler for ``HookEvent.ON_GDPR_REQUEST_SUBMITTED``.

    The GDPR service emits this with ``request`` (GdprRequest row)
    and ``user`` (User who submitted). We schedule the email
    dispatch as a background task so the originating request
    returns 202 immediately.
    """
    user = cast(User | None, kwargs.get("user"))
    request_obj = kwargs.get("request")
    if user is None or request_obj is None:
        return
    reason: str | None = getattr(request_obj, "reason", None)
    asyncio.create_task(
        _dispatch_gdpr_request(
            requester_id=user.id,
            requester_username=user.username,
            reason=reason,
        ),
        name="email-gdpr_request_submitted",
    )
