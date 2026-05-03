"""Service-level tests for ``policy_pages`` — Phase PP-F.

Covers:

1. ``validate_content`` enforces required fields, integer bounds,
   enum membership, localized-shape, and silently drops platform
   fields the form might echo back.
2. ``save_draft`` creates a row at v1 on first call, v2 on second,
   and writes a ``policy_page.saved`` audit row.
3. ``publish_version`` flips ``policy_pages.published_version_id``
   to the requested version and emits ``policy_page.published``.
4. ``unpublish`` clears the pointer.
5. ``build_render_context`` resolves localized values per the
   requested locale, falls back to EN, then to any present locale,
   and evaluates ``platform`` field ``source()`` callables.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError
from app.models.audit_log import AuditLog
from app.models.user import User
from app.plugins.policy_pages import service
from app.plugins.policy_pages.templates import get_template
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate


# ── Validation ────────────────────────────────────────────────────────────────


def test_validate_required_field_missing() -> None:
    template = get_template("mission")
    with pytest.raises(DomainValidationError) as exc:
        service.validate_content(template, {})
    assert "POLICY_FIELD_REQUIRED" in str(exc.value.code)


def test_validate_localized_shape() -> None:
    template = get_template("mission")
    out = service.validate_content(
        template,
        {
            "mission_statement": {"it": "Missione", "en": "Mission"},
            "scope": {"it": "Ambito", "en": "Scope"},
            "target_community": {"it": "Comunità", "en": "Community"},
        },
    )
    assert out["mission_statement"] == {"it": "Missione", "en": "Mission"}
    # platform fields silently dropped
    assert "aracne_version" not in out


def test_validate_integer_bounds() -> None:
    template = get_template("storage_policy")
    base = {
        "offsite_target": {"it": "S3", "en": "S3"},
        "rpo_hours": 0,  # below min=1
        "rto_hours": 24,
        "key_custodian": {"it": "Maria", "en": "Maria"},
        "restore_rehearsal_cadence": "monthly",
    }
    with pytest.raises(DomainValidationError):
        service.validate_content(template, base)


def test_validate_enum_membership() -> None:
    template = get_template("storage_policy")
    base = {
        "offsite_target": {"it": "S3", "en": "S3"},
        "rpo_hours": 1,
        "rto_hours": 24,
        "key_custodian": {"it": "Maria", "en": "Maria"},
        "restore_rehearsal_cadence": "yearly",  # not in options
    }
    with pytest.raises(DomainValidationError):
        service.validate_content(template, base)


def test_validate_rows_field() -> None:
    template = get_template("editorial_board")
    out = service.validate_content(
        template,
        {
            "board_members": [
                {
                    "name": "Anna",
                    "role": {"it": "Presidente", "en": "Chair"},
                    "affiliation": {"it": "UniRoma", "en": "UniRoma"},
                    "orcid": "0000-0001-2345-6789",
                }
            ]
        },
    )
    assert out["board_members"][0]["name"] == "Anna"
    assert out["board_members"][0]["role"]["en"] == "Chair"


# ── Save / publish / unpublish ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_first_then_second_increments_version(
    db_session: AsyncSession, seeded_admin: User
) -> None:
    content_v1 = {
        "mission_statement": {"it": "v1 IT", "en": "v1 EN"},
        "scope": {"it": "v1", "en": "v1"},
        "target_community": {"it": "v1", "en": "v1"},
    }
    v1 = await service.save_draft(
        db_session,
        template_slug="mission",
        content=content_v1,
        actor=seeded_admin,
    )
    assert v1.version_number == 1
    v2 = await service.save_draft(
        db_session,
        template_slug="mission",
        content={**content_v1, "mission_statement": {"it": "v2 IT", "en": "v2 EN"}},
        actor=seeded_admin,
    )
    assert v2.version_number == 2


@pytest.mark.asyncio
async def test_save_writes_audit_row(
    db_session: AsyncSession, seeded_admin: User
) -> None:
    await service.save_draft(
        db_session,
        template_slug="mission",
        content={
            "mission_statement": {"it": "x", "en": "x"},
            "scope": {"it": "x", "en": "x"},
            "target_community": {"it": "x", "en": "x"},
        },
        actor=seeded_admin,
    )
    rows = list(
        await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "policy_page.saved")
        )
    )
    assert any(r.target_id == "mission" for r in rows)


@pytest.mark.asyncio
async def test_publish_unpublish_round_trip(
    db_session: AsyncSession, seeded_admin: User
) -> None:
    v1 = await service.save_draft(
        db_session,
        template_slug="mission",
        content={
            "mission_statement": {"it": "x", "en": "x"},
            "scope": {"it": "x", "en": "x"},
            "target_community": {"it": "x", "en": "x"},
        },
        actor=seeded_admin,
    )
    page = await service.publish_version(
        db_session,
        template_slug="mission",
        version_number=v1.version_number,
        actor=seeded_admin,
    )
    assert page.published_version_id == v1.id

    page2 = await service.unpublish(
        db_session, template_slug="mission", actor=seeded_admin
    )
    assert page2.published_version_id is None


# ── Render context ────────────────────────────────────────────────────────────


def _tiny_template() -> PolicyTemplate:
    """Minimal template with one platform field + one localized field."""
    return PolicyTemplate(
        slug="_tiny",
        title_key="t.title",
        categories=("test",),
        fields=(
            Field("ver", "platform", source=lambda: "1.0.0",
                  label_key="t.ver"),
            Field("body", "textarea", localized=True,
                  label_key="t.body"),
        ),
        public_template="_default.md.j2",
    )


def test_render_context_resolves_platform_and_localized() -> None:
    template = _tiny_template()
    ctx = service.build_render_context(
        template,
        content={"body": {"it": "ciao", "en": "hello"}},
        locale="it",
        version=None,
        title="Tiny",
    )
    sections = {s["name"]: s for s in ctx["sections"]}
    assert sections["ver"]["value"] == "1.0.0"
    assert sections["ver"]["kind"] == "platform"
    assert sections["body"]["value"] == "ciao"


def test_render_context_falls_back_to_en() -> None:
    template = _tiny_template()
    ctx = service.build_render_context(
        template,
        content={"body": {"en": "english only"}},
        locale="it",
        version=None,
        title="Tiny",
    )
    body = next(s for s in ctx["sections"] if s["name"] == "body")
    assert body["value"] == "english only"


def test_render_context_handles_missing_platform_source() -> None:
    """A field whose ``source`` raises returns ``None`` rather than
    crashing the public render."""
    def boom() -> str:
        raise RuntimeError("nope")

    template = PolicyTemplate(
        slug="_boom",
        title_key="t.title",
        categories=("test",),
        fields=(
            Field("ver", "platform", source=boom, label_key="t.ver"),
        ),
        public_template="_default.md.j2",
    )
    ctx = service.build_render_context(
        template,
        content={},
        locale="en",
        version=None,
        title="Boom",
    )
    assert ctx["sections"][0]["value"] is None
