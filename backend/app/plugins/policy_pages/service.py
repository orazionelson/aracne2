"""Service layer for ``policy_pages`` — Phase PP-F.

Responsibilities:

1. **CRUD on the policy_pages row** — lazy creation on first edit
   (no row exists until the operator first opens a template's
   form), Save = new ``policy_page_versions`` row, Publish =
   point ``policy_pages.published_version_id`` at the chosen
   version, Unpublish = clear the pointer.
2. **Validation against the template** — operator-supplied values
   are type-checked against the template's :class:`Field`
   declarations (required, integer bounds, enum membership,
   rows-row consistency). Platform fields are never validated:
   they're computed at render time, not stored.
3. **Render context** — :func:`build_render_context` walks the
   template's fields, resolves each (operator value from the
   stored content, platform value via ``source()``), and emits
   the section list the public Markdown template iterates over.

Plain async functions — no class wrapper. Mirrors the rest of
``app/services/``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.models.audit_log import AuditLog
from app.models.policy_page import PolicyPage, PolicyPageVersion
from app.models.user import User
from app.plugins.policy_pages.templates import get_template, load_all
from app.plugins.policy_pages.templates._base import Field, PolicyTemplate

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_json(payload: dict[str, Any]) -> str:
    """Stable JSON serialisation for SHA-256 fingerprinting."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ── Validation ────────────────────────────────────────────────────────────────


def _validate_localized(value: Any, *, name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise DomainValidationError(
            "POLICY_FIELD_INVALID",
            f"Field '{name}' must be a per-locale object {{it, en}}.",
        )
    out: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{name}' has a non-string locale key.",
            )
        if v is None:
            out[k] = ""
        elif isinstance(v, str):
            out[k] = v
        else:
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{name}' has a non-string value for locale '{k}'.",
            )
    return out


def _validate_field(field: Field, value: Any) -> Any:
    """Coerce + validate one operator-supplied value against the field.

    Returns the canonicalised value to store under
    ``content_jsonb[field.name]``. Raises
    :class:`DomainValidationError` on any constraint violation.
    """
    if field.is_platform():
        # Platform fields are never operator-supplied — silently drop
        # any value the form sends so a stale form can't accidentally
        # override the live source.
        return None
    if value is None or value == "":
        if field.required:
            raise DomainValidationError(
                "POLICY_FIELD_REQUIRED",
                f"Field '{field.name}' is required.",
            )
        return None

    if field.kind in ("text", "textarea"):
        if field.localized:
            return _validate_localized(value, name=field.name)
        if not isinstance(value, str):
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{field.name}' must be a string.",
            )
        return value

    if field.kind == "integer":
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{field.name}' must be an integer.",
            ) from None
        if field.min is not None and n < field.min:
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{field.name}' must be ≥ {field.min}.",
            )
        if field.max is not None and n > field.max:
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{field.name}' must be ≤ {field.max}.",
            )
        return n

    if field.kind == "enum":
        if not isinstance(value, str) or value not in field.options:
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{field.name}' must be one of {list(field.options)}.",
            )
        return value

    if field.kind == "rows":
        if not isinstance(value, list):
            raise DomainValidationError(
                "POLICY_FIELD_INVALID",
                f"Field '{field.name}' must be a list of rows.",
            )
        out_rows: list[dict[str, Any]] = []
        for i, raw_row in enumerate(value):
            if not isinstance(raw_row, dict):
                raise DomainValidationError(
                    "POLICY_FIELD_INVALID",
                    f"Field '{field.name}' row {i} must be an object.",
                )
            row_out: dict[str, Any] = {}
            for sub in field.rows_fields:
                row_out[sub.name] = _validate_field(sub, raw_row.get(sub.name))
            out_rows.append(row_out)
        return out_rows

    raise DomainValidationError(
        "POLICY_FIELD_INVALID",
        f"Field '{field.name}' has unknown kind '{field.kind}'.",
    )


def validate_content(
    template: PolicyTemplate, content: dict[str, Any]
) -> dict[str, Any]:
    """Validate + canonicalise the operator-supplied content.

    Drops platform-field entries silently; coerces operator fields;
    raises :class:`DomainValidationError` on any constraint
    violation. The returned dict is what gets stored as
    ``policy_page_versions.content_jsonb``.
    """
    out: dict[str, Any] = {}
    for field in template.fields:
        if field.is_platform():
            continue
        coerced = _validate_field(field, content.get(field.name))
        # Skip empty optional fields rather than persisting null —
        # keeps the JSONB lean and the canonical SHA-256 stable.
        if coerced is None:
            continue
        out[field.name] = coerced
    return out


# ── Lookups ───────────────────────────────────────────────────────────────────


async def get_or_create_page(
    db: AsyncSession, *, template_slug: str
) -> PolicyPage:
    """Return the page row for *template_slug*, creating it if needed.

    Raises :class:`NotFoundError` when *template_slug* is not in
    the built-in catalogue.
    """
    template = get_template(template_slug)
    existing = await db.scalar(
        select(PolicyPage).where(PolicyPage.template_slug == template_slug)
    )
    if existing is not None:
        return existing
    row = PolicyPage(
        template_slug=template.slug,
        slug=template.url_slug(),
    )
    db.add(row)
    await db.flush()
    return row


async def get_page_by_url_slug(
    db: AsyncSession, *, url_slug: str
) -> PolicyPage | None:
    """Lookup helper used by the public render path."""
    return await db.scalar(select(PolicyPage).where(PolicyPage.slug == url_slug))


async def list_pages(db: AsyncSession) -> list[dict[str, Any]]:
    """Return one entry per built-in template, with the row's
    current state (or ``None`` if no row exists yet).

    Drives the admin list view: the operator sees every available
    template even when they haven't started editing one yet.
    """
    rows = list(await db.scalars(select(PolicyPage)))
    by_template = {r.template_slug: r for r in rows}
    out: list[dict[str, Any]] = []
    for slug, template in load_all().items():
        page = by_template.get(slug)
        latest_version = None
        if page is not None:
            latest_version = await db.scalar(
                select(PolicyPageVersion)
                .where(PolicyPageVersion.policy_page_id == page.id)
                .order_by(desc(PolicyPageVersion.version_number))
                .limit(1)
            )
        out.append(
            {
                "template_slug": slug,
                "url_slug": template.url_slug(),
                "title_key": template.title_key,
                "categories": list(template.categories),
                "is_published": page is not None and page.published_version_id is not None,
                "latest_version_number": (
                    latest_version.version_number if latest_version else None
                ),
                "latest_saved_at": (
                    latest_version.saved_at.isoformat() if latest_version else None
                ),
            }
        )
    return out


async def get_latest_version(
    db: AsyncSession, *, page_id: uuid.UUID
) -> PolicyPageVersion | None:
    return await db.scalar(
        select(PolicyPageVersion)
        .where(PolicyPageVersion.policy_page_id == page_id)
        .order_by(desc(PolicyPageVersion.version_number))
        .limit(1)
    )


async def list_versions(
    db: AsyncSession, *, page_id: uuid.UUID
) -> Sequence[PolicyPageVersion]:
    return list(
        await db.scalars(
            select(PolicyPageVersion)
            .where(PolicyPageVersion.policy_page_id == page_id)
            .order_by(desc(PolicyPageVersion.version_number))
        )
    )


# ── Save / Publish / Unpublish ────────────────────────────────────────────────


async def _next_version_number(
    db: AsyncSession, *, page_id: uuid.UUID
) -> int:
    n = await db.scalar(
        select(func.coalesce(func.max(PolicyPageVersion.version_number), 0)).where(
            PolicyPageVersion.policy_page_id == page_id
        )
    )
    return int(n or 0) + 1


async def save_draft(
    db: AsyncSession,
    *,
    template_slug: str,
    content: dict[str, Any],
    actor: User,
    message: str | None = None,
) -> PolicyPageVersion:
    """Save a new draft version. Does NOT touch ``published_version_id``.

    The caller's authorisation is enforced upstream by the router
    via ``require_capability("PolicyManager")``; this function
    trusts the caller is allowed to write.
    """
    template = get_template(template_slug)
    canonical = validate_content(template, content)
    page = await get_or_create_page(db, template_slug=template_slug)
    version_number = await _next_version_number(db, page_id=page.id)

    row = PolicyPageVersion(
        policy_page_id=page.id,
        version_number=version_number,
        content_jsonb=canonical,
        content_sha256=_sha256(canonical),
        message=message,
        saved_by_id=actor.id,
    )
    db.add(row)
    page.updated_at = _now()
    db.add(
        AuditLog(
            action="policy_page.saved",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="policy_page",
            target_id=template_slug,
            target_label=template_slug,
            payload={"version_number": version_number},
        )
    )
    await db.flush()
    logger.info(
        "policy_page_saved",
        template_slug=template_slug,
        version=version_number,
        actor=actor.username,
    )
    return row


async def publish_version(
    db: AsyncSession,
    *,
    template_slug: str,
    version_number: int | None = None,
    actor: User,
) -> PolicyPage:
    """Promote a version to public. ``version_number=None`` publishes
    the most-recent draft.

    Raises :class:`NotFoundError` if no version exists yet, or
    :class:`ConflictError` if the requested ``version_number`` is
    not a row of this page.
    """
    page = await get_or_create_page(db, template_slug=template_slug)
    if version_number is None:
        latest = await get_latest_version(db, page_id=page.id)
        if latest is None:
            raise NotFoundError(
                f"Policy '{template_slug}' has no saved versions yet."
            )
        target = latest
    else:
        target = await db.scalar(
            select(PolicyPageVersion).where(
                PolicyPageVersion.policy_page_id == page.id,
                PolicyPageVersion.version_number == version_number,
            )
        )
        if target is None:
            raise ConflictError(
                f"Policy '{template_slug}' has no version {version_number}."
            )

    page.published_version_id = target.id
    page.updated_at = _now()
    db.add(
        AuditLog(
            action="policy_page.published",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="policy_page",
            target_id=template_slug,
            target_label=template_slug,
            payload={"version_number": target.version_number},
        )
    )
    await db.flush()
    logger.info(
        "policy_page_published",
        template_slug=template_slug,
        version=target.version_number,
        actor=actor.username,
    )
    return page


async def unpublish(
    db: AsyncSession, *, template_slug: str, actor: User
) -> PolicyPage:
    """Clear ``published_version_id``. The page becomes draft-only;
    the public ``/policies/<slug>`` route 404s."""
    page = await db.scalar(
        select(PolicyPage).where(PolicyPage.template_slug == template_slug)
    )
    if page is None:
        raise NotFoundError(f"Policy '{template_slug}' has no row yet.")
    page.published_version_id = None
    page.updated_at = _now()
    db.add(
        AuditLog(
            action="policy_page.unpublished",
            actor_id=actor.id,
            actor_username=actor.username,
            target_type="policy_page",
            target_id=template_slug,
            target_label=template_slug,
            payload={},
        )
    )
    await db.flush()
    return page


# ── Render context ────────────────────────────────────────────────────────────


def _resolve_field_value(
    field: Field, content: dict[str, Any], locale: str
) -> Any:
    """Return the public-render value for one field.

    - For platform fields: invoke ``source()`` synchronously; on
      exception fall back to ``None`` so a transient introspection
      failure doesn't crash the public render.
    - For localized text/textarea fields: prefer the requested
      ``locale``, fall back to EN, then to any locale present, then
      to ``None``.
    - For ``rows`` fields: recurse on each row's sub-fields.
    - For everything else: pass through the stored value.
    """
    if field.is_platform():
        if field.source is None:
            return None
        try:
            return field.source()
        except Exception as exc:  # noqa: BLE001 — never crash the render
            logger.warning(
                "policy_platform_source_failed",
                field=field.name,
                error=str(exc),
            )
            return None

    raw = content.get(field.name)
    if raw is None:
        return None

    if field.kind in ("text", "textarea") and field.localized:
        if isinstance(raw, dict):
            if locale in raw and raw[locale]:
                return raw[locale]
            if "en" in raw and raw["en"]:
                return raw["en"]
            for v in raw.values():
                if v:
                    return v
        return None

    if field.kind == "rows":
        if not isinstance(raw, list):
            return []
        out: list[list[Any]] = []
        for row in raw:
            cells: list[Any] = []
            for sub in field.rows_fields:
                cells.append(_resolve_field_value(sub, row if isinstance(row, dict) else {}, locale))
            out.append(cells)
        return out

    return raw


def build_render_context(
    template: PolicyTemplate,
    *,
    content: dict[str, Any],
    locale: str,
    version: PolicyPageVersion | None,
    title: str,
    i18n: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the dict the Jinja2 ``_default.md.j2`` template iterates.

    *i18n* is an optional ``label_key -> localised string`` map the
    caller supplies (admin form vs. public render may want
    different label resolution paths). When absent, labels fall
    back to the field ``name``.

    The returned shape:

    ```jsonc
    {
      "title": "Storage policy",
      "locale": "en",
      "version": {"number": 3, "saved_at": "...", "saved_by": "..."},
      "sections": [
        {
          "label": "Postgres version",
          "kind": "platform",
          "value": "16.2",
          "row_labels": [],
          "rows": [],
        },
        ...
      ],
    }
    ```
    """
    i18n = i18n or {}
    sections: list[dict[str, Any]] = []
    for f in template.fields:
        label = i18n.get(f.label_key or "", f.label_key or f.name)
        section: dict[str, Any] = {
            "name": f.name,
            "label": label,
            "kind": f.kind,
            "value": _resolve_field_value(f, content, locale),
            "row_labels": (
                [
                    i18n.get(sub.label_key or "", sub.label_key or sub.name)
                    for sub in f.rows_fields
                ]
                if f.kind == "rows"
                else []
            ),
        }
        if f.kind == "rows":
            section["rows"] = section["value"] or []
            section["value"] = None
        else:
            section["rows"] = []
        sections.append(section)

    saved_by_label: str | None = None
    if version is not None and version.saved_by_id is not None:
        # Resolve username lazily — caller should pre-load when many
        # versions are listed at once. For the single-render path we
        # leave it None and let the caller fill it in.
        saved_by_label = None

    return {
        "title": title,
        "locale": locale,
        "version": {
            "number": version.version_number if version is not None else None,
            "saved_at": version.saved_at.isoformat() if version is not None else None,
            "saved_by": saved_by_label,
        },
        "sections": sections,
    }


__all__ = [
    "validate_content",
    "save_draft",
    "publish_version",
    "unpublish",
    "list_pages",
    "list_versions",
    "get_or_create_page",
    "get_page_by_url_slug",
    "get_latest_version",
    "build_render_context",
]
