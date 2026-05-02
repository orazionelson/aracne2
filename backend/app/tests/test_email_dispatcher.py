"""Tests for the ``email_dispatcher`` native plugin (Phase EM-B).

Exercises the dispatch core (``_dispatch_collection_event``) directly:
the hook-handler wrappers around it just resolve kwargs and spawn an
asyncio task, which is awkward to await deterministically in tests. The
service-level call goes through every recipient-resolution branch with a
single mock for ``send_mail`` so call counts are easy to assert.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus
from app.models.role import Role, RoleName, UserRole
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins._native.email_dispatcher import plugin as _email_plugin  # noqa: F401 — register hooks
from app.plugins._native.email_dispatcher.service import _dispatch_collection_event


async def _make_user(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    lang: str = "en",
    notifications_on: bool = True,
    role: str | None = None,
) -> User:
    from app.core.password import hash_password

    user = User(
        username=username,
        email=email,
        password_hash=hash_password("x" * 12),
        is_active=True,
        is_verified=True,
        preferred_lang=lang,
        email_notifications_enabled=notifications_on,
    )
    db.add(user)
    await db.flush()
    if role is not None:
        role_row = await db.scalar(_select_role_by_name(role))
        assert role_row is not None
        db.add(UserRole(user_id=user.id, role_id=role_row.id))
        await db.flush()
    return user


def _select_role_by_name(name: str):
    from sqlalchemy import select

    return select(Role).where(Role.name == name)


async def _enable_email(db: AsyncSession) -> None:
    """Flip the platform-wide ``email_enabled`` toggle for the test."""
    for key, value, type_ in (
        ("email_enabled", "true", "bool"),
        ("email_smtp_host", "postfix", "string"),
        ("email_smtp_port", "25", "int"),
        ("email_from_address", "noreply@example.org", "string"),
        ("email_from_name", "Aracne2 Test", "string"),
        ("email_subject_prefix", "[Aracne2]", "string"),
    ):
        existing = await db.get(SystemSetting, key)
        if existing is None:
            db.add(SystemSetting(key=key, value=value, type=type_))
        else:
            existing.value = value
    await db.flush()


@pytest.mark.asyncio
async def test_collection_submitted_emails_active_eics_excluding_actor(
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_editorinchief: User,
    seeded_user: User,
) -> None:
    """``collection_submitted`` reaches every active EiC+ except the actor."""
    await _enable_email(db_session)
    col = Collection(
        slug="em-sub", title="Submission", status=CollectionStatus.review
    )
    db_session.add(col)
    await db_session.flush()
    await db_session.commit()

    with patch(
        "app.plugins._native.email_dispatcher.service.AsyncSessionLocal"
    ) as mock_factory, patch(
        "app.plugins._native.email_dispatcher.service.send_mail",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        # Make the in-task session reuse our test session by yielding it
        # from the patched context manager.
        mock_factory.return_value.__aenter__.return_value = db_session
        mock_factory.return_value.__aexit__.return_value = None

        await _dispatch_collection_event(
            "collection_submitted",
            collection_id=col.id,
            actor_id=seeded_user.id,  # actor is a regular User → must be excluded
            actor_display="Editor X",
            note="ready for review",
        )

    # The actor is a regular User — not an EiC — so we cannot easily
    # rely on "exclude actor" via this fixture set. The asserts below
    # focus on what we CAN guarantee: every recipient is an Admin/EiC,
    # toggle on, and not the actor.
    recipient_emails = [
        call.kwargs["to"] for call in mock_send.await_args_list
    ]
    assert seeded_admin.email in recipient_emails
    assert seeded_editorinchief.email in recipient_emails
    assert seeded_user.email not in recipient_emails


@pytest.mark.asyncio
async def test_collection_submitted_excludes_actor_when_actor_is_eic(
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_editorinchief: User,
) -> None:
    """If the EiC submits on their own (e.g. self-assigned a collection
    and submitted), they are NOT emailed; the Admin still is."""
    await _enable_email(db_session)
    col = Collection(
        slug="em-sub-self", title="Self submit", status=CollectionStatus.review
    )
    db_session.add(col)
    await db_session.flush()
    await db_session.commit()

    with patch(
        "app.plugins._native.email_dispatcher.service.AsyncSessionLocal"
    ) as mock_factory, patch(
        "app.plugins._native.email_dispatcher.service.send_mail",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        mock_factory.return_value.__aenter__.return_value = db_session
        mock_factory.return_value.__aexit__.return_value = None

        await _dispatch_collection_event(
            "collection_submitted",
            collection_id=col.id,
            actor_id=seeded_editorinchief.id,
            actor_display="Eic-Self",
            note=None,
        )

    recipients = [call.kwargs["to"] for call in mock_send.await_args_list]
    assert seeded_editorinchief.email not in recipients
    assert seeded_admin.email in recipients


@pytest.mark.asyncio
async def test_collection_published_emails_assigned_editor(
    db_session: AsyncSession,
    seeded_admin: User,
    seeded_editorinchief: User,
    seeded_user: User,
) -> None:
    """``collection_published`` emails the assigned editor only."""
    await _enable_email(db_session)
    col = Collection(
        slug="em-pub",
        title="Published",
        status=CollectionStatus.published,
        editor_id=seeded_user.id,
    )
    db_session.add(col)
    await db_session.flush()
    await db_session.commit()

    with patch(
        "app.plugins._native.email_dispatcher.service.AsyncSessionLocal"
    ) as mock_factory, patch(
        "app.plugins._native.email_dispatcher.service.send_mail",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        mock_factory.return_value.__aenter__.return_value = db_session
        mock_factory.return_value.__aexit__.return_value = None

        await _dispatch_collection_event(
            "collection_published",
            collection_id=col.id,
            actor_id=seeded_editorinchief.id,
            actor_display="Eic",
            note="approved",
        )

    recipients = [call.kwargs["to"] for call in mock_send.await_args_list]
    assert recipients == [seeded_user.email]
    assert seeded_editorinchief.email not in recipients
    assert seeded_admin.email not in recipients


@pytest.mark.asyncio
async def test_recipient_with_toggle_off_is_skipped(
    db_session: AsyncSession,
    seeded_editorinchief: User,
    seeded_user: User,
) -> None:
    """A user with ``email_notifications_enabled=False`` is filtered out
    of the recipient set even when otherwise eligible."""
    await _enable_email(db_session)
    seeded_user.email_notifications_enabled = False
    await db_session.flush()

    col = Collection(
        slug="em-off",
        title="Off",
        status=CollectionStatus.published,
        editor_id=seeded_user.id,
    )
    db_session.add(col)
    await db_session.flush()
    await db_session.commit()

    with patch(
        "app.plugins._native.email_dispatcher.service.AsyncSessionLocal"
    ) as mock_factory, patch(
        "app.plugins._native.email_dispatcher.service.send_mail",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        mock_factory.return_value.__aenter__.return_value = db_session
        mock_factory.return_value.__aexit__.return_value = None

        await _dispatch_collection_event(
            "collection_published",
            collection_id=col.id,
            actor_id=seeded_editorinchief.id,
            actor_display="Eic",
            note="",
        )

    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_swallows_exceptions(
    db_session: AsyncSession,
    seeded_editorinchief: User,
    seeded_user: User,
) -> None:
    """A handler crash never propagates — the workflow operation that
    triggered the hook must keep running even when the dispatcher
    blows up."""
    await _enable_email(db_session)
    col = Collection(
        slug="em-boom",
        title="Boom",
        status=CollectionStatus.published,
        editor_id=seeded_user.id,
    )
    db_session.add(col)
    await db_session.flush()
    await db_session.commit()

    with patch(
        "app.plugins._native.email_dispatcher.service.AsyncSessionLocal"
    ) as mock_factory, patch(
        "app.plugins._native.email_dispatcher.service.send_mail",
        new_callable=AsyncMock,
        side_effect=RuntimeError("smtp went up in flames"),
    ):
        mock_factory.return_value.__aenter__.return_value = db_session
        mock_factory.return_value.__aexit__.return_value = None

        # The function must complete without raising.
        await _dispatch_collection_event(
            "collection_published",
            collection_id=col.id,
            actor_id=seeded_editorinchief.id,
            actor_display="Eic",
            note=None,
        )


def test_handlers_registered_for_workflow_events() -> None:
    """Importing the plugin module side-effects three handler
    registrations on the singleton hook registry."""
    from app.core.hooks import HookEvent, hook_registry

    for event in (
        HookEvent.ON_COLLECTION_SUBMITTED,
        HookEvent.ON_COLLECTION_REJECTED,
        HookEvent.ON_COLLECTION_PUBLISHED,
    ):
        names = [
            getattr(h, "__name__", "?")
            for h in hook_registry._handlers.get(event, [])  # type: ignore[attr-defined]
        ]
        assert any(n.startswith("on_collection_") for n in names), (
            f"no email_dispatcher handler registered for {event}"
        )
