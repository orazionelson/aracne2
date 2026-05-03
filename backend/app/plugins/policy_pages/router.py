"""HTTP entrypoint for ``policy_pages`` — Phase PP-F.

REST surface:

- **Admin / read-only for E+, write for PolicyManager + Admin**:
  - ``GET    /policy-pages``                  — list templates
  - ``GET    /policy-pages/{slug}``           — hydrate the form
  - ``GET    /policy-pages/{slug}/versions``  — full version history
  - ``POST   /policy-pages/{slug}/save``      — save a new draft
  - ``POST   /policy-pages/{slug}/publish``   — promote a version
  - ``POST   /policy-pages/{slug}/unpublish`` — clear the pointer
- **Public**:
  - ``GET    /policies``                      — index of published policies
  - ``GET    /policies/{url_slug}``           — render a published page

The split between ``/policy-pages`` (admin) and ``/policies``
(public) keeps the auth posture clean: admin endpoints take
``Authorization: Bearer …``; public endpoints are anonymous.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from jinja2 import (
    Environment,
    FileSystemLoader,
    select_autoescape,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import require_capability, require_role
from app.middleware.rate_limiter import limiter
from app.models.policy_page import PolicyPageVersion
from app.models.user import User
from app.schemas.common import DataResponse
from app.services.settings import get_decrypted_setting

from app.plugins.policy_pages import service
from app.plugins.policy_pages.schemas import (
    PolicyPageDetail,
    PolicyPageListItem,
    PolicyPageVersionView,
    PolicyRenderResponse,
    PolicyTemplateDescriptor,
    PublishRequest,
    SaveDraftRequest,
)
from app.plugins.policy_pages.templates import get_template
from app.plugins.policy_pages.templates._base import PolicyTemplate

router = APIRouter(tags=["policy_pages"])

# ── Auth shortcuts ────────────────────────────────────────────────────────────

# Editor+ can read drafts (for review). Capability gate sits on the
# write endpoints; on read we use a hierarchical min-role check.
_e_plus = Depends(require_role(min_role="Editor"))
_writer = Depends(require_capability("PolicyManager"))


# ── Markdown render — shared Jinja2 env ───────────────────────────────────────

_MD_DIR = Path(__file__).parent / "public_md"
_md_env = Environment(
    loader=FileSystemLoader(str(_MD_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
    keep_trailing_newline=True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _resolve_platform_values(
    template: PolicyTemplate,
) -> dict[str, object]:
    """Pre-evaluate every ``platform`` field's ``source()`` so the
    admin form can render the current values inline."""
    out: dict[str, object] = {}
    for f in template.platform_fields():
        if f.source is None:
            out[f.name] = None
            continue
        try:
            out[f.name] = f.source()
        except Exception:  # noqa: BLE001 — never crash the form load
            out[f.name] = None
    return out


def _template_to_descriptor(template: PolicyTemplate) -> PolicyTemplateDescriptor:
    return PolicyTemplateDescriptor.model_validate(template.to_descriptor())


async def _resolve_locale(
    db: AsyncSession, override: str | None
) -> str:
    """Pick a locale for a public render: explicit ``?lang=`` query
    wins; otherwise the platform's ``default_language`` setting;
    otherwise English."""
    if override and override.split("-")[0].lower() in ("it", "en"):
        return override.split("-")[0].lower()
    default = (await get_decrypted_setting(db, "default_language") or "en").strip().lower()
    if default not in ("it", "en"):
        default = "en"
    return default


# ── Admin: list templates ─────────────────────────────────────────────────────


@router.get("/policy-pages")
@limiter.limit("60/minute")
async def list_policies(
    request: Request,
    current_user: Annotated[User, _e_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[PolicyPageListItem]]:
    """List every built-in template plus its current state."""
    items = await service.list_pages(db)
    return DataResponse(
        data=[PolicyPageListItem.model_validate(i) for i in items]
    )


# ── Admin: form hydration ─────────────────────────────────────────────────────


@router.get("/policy-pages/{slug}")
@limiter.limit("60/minute")
async def get_policy(
    request: Request,
    slug: str,
    current_user: Annotated[User, _e_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PolicyPageDetail]:
    """Return the descriptor + the latest content for the form."""
    try:
        template = get_template(slug)
    except KeyError as exc:
        raise NotFoundError(f"Policy template '{slug}' not found") from exc

    page = await service.get_or_create_page(db, template_slug=slug)
    latest = await service.get_latest_version(db, page_id=page.id)
    detail = PolicyPageDetail(
        template=_template_to_descriptor(template),
        is_published=page.published_version_id is not None,
        published_version_number=None,
        latest_version_number=latest.version_number if latest else None,
        latest_content=dict(latest.content_jsonb) if latest else {},
        platform_values=await _resolve_platform_values(template),
    )
    if page.published_version_id is not None:
        published = await db.get(PolicyPageVersion, page.published_version_id)
        if published is not None:
            detail.published_version_number = published.version_number
    return DataResponse(data=detail)


# ── Admin: version history ────────────────────────────────────────────────────


@router.get("/policy-pages/{slug}/versions")
@limiter.limit("60/minute")
async def list_versions(
    request: Request,
    slug: str,
    current_user: Annotated[User, _e_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[PolicyPageVersionView]]:
    page = await service.get_or_create_page(db, template_slug=slug)
    versions = await service.list_versions(db, page_id=page.id)
    out: list[PolicyPageVersionView] = []
    published_id = page.published_version_id
    for v in versions:
        # Resolve the saved-by username lazily — small enough loop
        # for the version-history page (typical N << 100).
        saved_by_username: str | None = None
        if v.saved_by_id is not None:
            user = await db.get(User, v.saved_by_id)
            if user is not None:
                saved_by_username = user.username
        out.append(
            PolicyPageVersionView(
                id=v.id,
                version_number=v.version_number,
                content_sha256=v.content_sha256,
                message=v.message,
                saved_at=v.saved_at,
                saved_by_username=saved_by_username,
                is_published=(v.id == published_id),
            )
        )
    return DataResponse(data=out)


# ── Admin: write surface (PolicyManager + Admin only) ─────────────────────────


@router.post("/policy-pages/{slug}/save", status_code=201)
@limiter.limit("30/minute")
async def save_policy(
    request: Request,
    slug: str,
    body: SaveDraftRequest,
    current_user: Annotated[User, _writer],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PolicyPageVersionView]:
    row = await service.save_draft(
        db,
        template_slug=slug,
        content=body.content,
        actor=current_user,
        message=body.message,
    )
    saved_by_username: str | None = None
    if row.saved_by_id is not None:
        user = await db.get(User, row.saved_by_id)
        if user is not None:
            saved_by_username = user.username
    return DataResponse(
        data=PolicyPageVersionView(
            id=row.id,
            version_number=row.version_number,
            content_sha256=row.content_sha256,
            message=row.message,
            saved_at=row.saved_at,
            saved_by_username=saved_by_username,
            is_published=False,
        )
    )


@router.post("/policy-pages/{slug}/publish")
@limiter.limit("30/minute")
async def publish_policy(
    request: Request,
    slug: str,
    body: PublishRequest,
    current_user: Annotated[User, _writer],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PolicyPageDetail]:
    await service.publish_version(
        db,
        template_slug=slug,
        version_number=body.version_number,
        actor=current_user,
    )
    # Re-hydrate so the SPA can replace the form state with the
    # newly-published view in one round-trip.
    return await get_policy(  # type: ignore[return-value]
        request=request, slug=slug, current_user=current_user, db=db,
    )


@router.post("/policy-pages/{slug}/unpublish")
@limiter.limit("30/minute")
async def unpublish_policy(
    request: Request,
    slug: str,
    current_user: Annotated[User, _writer],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[PolicyPageDetail]:
    await service.unpublish(db, template_slug=slug, actor=current_user)
    return await get_policy(  # type: ignore[return-value]
        request=request, slug=slug, current_user=current_user, db=db,
    )


# ── Public: index + render ────────────────────────────────────────────────────


@router.get("/policies")
@limiter.limit("60/minute")
async def public_list(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[dict[str, object]]]:
    """Return the list of currently-published policies for the
    public ``/policies`` index page. Anonymous; no auth required."""
    items = await service.list_pages(db)
    return DataResponse(
        data=[
            {
                "url_slug": i["url_slug"],
                "template_slug": i["template_slug"],
                "title_key": i["title_key"],
                "categories": i["categories"],
            }
            for i in items
            if i["is_published"]
        ]
    )


@router.get("/policies/{url_slug}")
@limiter.limit("60/minute")
async def public_render(
    request: Request,
    url_slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    lang: Annotated[str | None, Query()] = None,
) -> DataResponse[PolicyRenderResponse]:
    """Render the currently-published version of a policy as HTML.

    Returns 404 when the slug is unknown OR when the page exists
    but has no published version. Anonymous; no auth required.
    """
    page = await service.get_page_by_url_slug(db, url_slug=url_slug)
    if page is None or page.published_version_id is None:
        raise NotFoundError(f"Policy '{url_slug}' is not published.")

    template = get_template(page.template_slug)
    version = await db.get(PolicyPageVersion, page.published_version_id)
    if version is None:
        raise NotFoundError(f"Policy '{url_slug}' has no readable version.")

    locale = await _resolve_locale(db, lang)
    # The Jinja2 renderer uses the field's ``label_key`` literal as
    # the section heading when no i18n map is supplied; the SPA
    # locale-resolves the markdown again client-side via vue-i18n.
    # That keeps the backend free of the frontend's locale catalogue.
    context = service.build_render_context(
        template,
        content=dict(version.content_jsonb),
        locale=locale,
        version=version,
        title=template.title_key,
    )

    saved_by_username: str | None = None
    if version.saved_by_id is not None:
        user = await db.get(User, version.saved_by_id)
        if user is not None:
            saved_by_username = user.username
    context["version"]["saved_by"] = saved_by_username

    md_template = _md_env.get_template(template.public_template)
    md_body = md_template.render(**context)

    # Markdown → HTML via the existing markdown-it pipeline used by
    # the help plugin. We import lazily so the help plugin's bleach
    # whitelist does not have to load when policy_pages is the only
    # caller of this code path.
    from markdown_it import MarkdownIt

    html = MarkdownIt("commonmark", {"html": False}).render(md_body)

    return DataResponse(
        data=PolicyRenderResponse(
            title=template.title_key,
            locale=locale,
            html=html,
            version_number=version.version_number,
            saved_at=version.saved_at,
            saved_by=saved_by_username,
        )
    )
