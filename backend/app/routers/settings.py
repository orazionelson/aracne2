import mimetypes
from typing import Annotated

import bleach
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.middleware.rate_limiter import limiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.settings import (
    HomepageCssUploadResponse,
    LogoUploadResponse,
    SettingResponse,
    SettingUpdate,
    UiConfigResponse,
)
from app.services.settings import (
    _MAX_CSS_BYTES,
    _MAX_LOGO_BYTES,
    delete_homepage_css,
    get_homepage_css_path,
    get_logo_path,
    get_public_config,
    get_setting,
    list_settings,
    update_setting,
    upload_homepage_css,
    upload_logo,
)
from app.services.uploads import read_capped

router = APIRouter(prefix="/settings", tags=["settings"])

_admin = Depends(require_role(min_role="Admin"))


# ── Public UI configuration ────────────────────────────────────────────────────
# Declared BEFORE /{key} so FastAPI does not treat "ui-config" as a key param.

@router.get("/ui-config")
async def settings_ui_config(
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[UiConfigResponse]:
    """Return the frontend UI configuration (platform name, logo URL, navbar
    colour).  No authentication required — the login page reads this too."""
    data = await get_public_config(db)
    return DataResponse(data=data)


# ── Logo upload / serve ────────────────────────────────────────────────────────

@router.post("/logo")
async def settings_logo_upload(
    file: UploadFile,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[LogoUploadResponse]:
    """Upload a new platform logo image [Admin].

    Accepted formats: .png .jpg .jpeg .gif .svg .webp
    The uploaded file is stored in MEDIA_DIR and the platform_logo_url
    setting is updated to point to the serve endpoint.
    """
    content = await read_capped(file, _MAX_LOGO_BYTES)
    data = await upload_logo(db, content, file.filename or "logo.png", current_user)
    return DataResponse(data=data)


@router.get("/logo/file")
@limiter.limit("120/minute")
async def settings_logo_file(request: Request) -> FileResponse:
    """Serve the uploaded platform logo file (public, no authentication).

    Returns 404 if no custom logo has been uploaded yet; the frontend falls
    back to the default /aracne-icons/lockup/aracne-lockup-vertical-512.png
    in that case (see backend/app/services/settings.py).
    """
    path = get_logo_path()
    if path is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No custom logo uploaded")
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(str(path), media_type=media_type or "image/png")


# ── Homepage CSS upload / serve / delete ──────────────────────────────────────

@router.post("/homepage-css")
async def settings_homepage_css_upload(
    file: UploadFile,
    current_user: Annotated[User, _admin],
) -> DataResponse[HomepageCssUploadResponse]:
    """Upload a custom homepage CSS file [Admin].

    The uploaded ``.css`` file is stored in MEDIA_DIR and served via the
    public ``GET /settings/homepage-css/file`` endpoint, which the public
    homepage injects as its last stylesheet.
    """
    content = await read_capped(file, _MAX_CSS_BYTES)
    data = await upload_homepage_css(content, file.filename or "custom_homepage.css", current_user)
    return DataResponse(data=data)


@router.get("/homepage-css/file")
@limiter.limit("120/minute")
async def settings_homepage_css_file(request: Request) -> FileResponse:
    """Serve the uploaded custom homepage CSS (public, no authentication).

    Returns 404 if no custom CSS has been uploaded yet.
    """
    path = get_homepage_css_path()
    if path is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No custom homepage CSS uploaded")
    return FileResponse(str(path), media_type="text/css")


@router.delete("/homepage-css", status_code=204)
async def settings_homepage_css_delete(
    current_user: Annotated[User, _admin],
) -> None:
    """Remove the custom homepage CSS file [Admin]."""
    await delete_homepage_css(current_user)


# ── Homepage media library + intro HTML ───────────────────────────────────────
#
# Shared media folder for the public Pagine Pubbliche surface. Same
# upload / list / delete pattern as the per-website media; a single
# pool because there is exactly one homepage per platform.
#
# Public read at ``GET /settings/homepage-media/{filename}`` so the
# rendered ``home_intro_html`` can carry stable absolute URLs into
# every visitor's browser.

from fastapi.responses import Response  # noqa: E402

from app.services import homepage_media as homepage_media_svc  # noqa: E402


@router.get("/homepage-media")
async def settings_homepage_media_list(
    current_user: Annotated[User, _admin],
) -> DataResponse[list[dict[str, object]]]:
    """List uploaded homepage media files [Admin]."""
    files = homepage_media_svc.list_media()
    return DataResponse(
        data=[
            {
                "filename": f.filename,
                "size_bytes": f.size_bytes,
                "content_type": f.content_type,
                "uploaded_at": f.uploaded_at.isoformat(),
                # Absolute serve path — homepage media lives at a fixed
                # endpoint with no slug, so the picker can paste this
                # straight into the WYSIWYG without needing a rewrite
                # layer at render time.
                "ref": f"/api/v1/settings/homepage-media/{f.filename}",
            }
            for f in files
        ]
    )


@router.post("/homepage-media")
async def settings_homepage_media_upload(
    file: UploadFile,
    current_user: Annotated[User, _admin],
) -> DataResponse[dict[str, object]]:
    """Upload an image into the homepage media folder [Admin]."""
    from app.services.website_media import _MAX_UPLOAD_BYTES

    content = await read_capped(file, _MAX_UPLOAD_BYTES)
    saved = homepage_media_svc.save_media(file.filename or "image", content)
    return DataResponse(
        data={
            "filename": saved.filename,
            "size_bytes": saved.size_bytes,
            "content_type": saved.content_type,
            "uploaded_at": saved.uploaded_at.isoformat(),
            "ref": f"/api/v1/settings/homepage-media/{saved.filename}",
        }
    )


@router.get("/homepage-media/{filename}")
@limiter.limit("120/minute")
async def settings_homepage_media_serve(
    filename: str, request: Request
) -> Response:
    """Serve a homepage media file (public, no authentication)."""
    payload, content_type = homepage_media_svc.read_media(filename)
    return Response(content=payload, media_type=content_type)


@router.delete("/homepage-media/{filename}", status_code=204)
async def settings_homepage_media_delete(
    filename: str,
    current_user: Annotated[User, _admin],
) -> None:
    """Delete a homepage media file [Admin]."""
    homepage_media_svc.delete_media(filename)


# ── Homepage intro HTML ───────────────────────────────────────────────────────
#
# Stored as a ``system_settings`` row keyed ``home_intro_html``. A
# dedicated endpoint bypasses ``SettingUpdate``'s ``not_empty``
# validator so admins can clear the intro by sending an empty string.
#
# The body is rendered with ``v-html`` on the public homepage, so we
# run it through ``bleach`` first with a strict tag/attribute allowlist.
# CSP already blocks inline scripts in production, but the sanitiser
# closes the gap for dev mode and protects against accidental paste of
# tracking pixels / third-party widgets the admin didn't realise were
# embedded in copied markup.

# Tags an admin can put in the cover text. No <script>, no <iframe>,
# no <style> — those carry execution / framing surfaces we don't want.
_HOME_INTRO_ALLOWED_TAGS: frozenset[str] = frozenset({
    "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "h2", "h3", "h4",
    "a", "img", "figure", "figcaption", "hr", "span",
})
_HOME_INTRO_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "span": ["class"],
}
# `media://` is rewritten client-side to a same-origin URL — see
# useHomepageMedia. The other two are the only schemes we want for
# href / src outside of bare relative paths.
_HOME_INTRO_ALLOWED_PROTOCOLS: list[str] = ["http", "https", "media"]
_HOME_INTRO_MAX_BYTES: int = 64 * 1024  # 64 KB UTF-8


def _sanitise_home_intro(raw: str) -> str:
    """Apply size cap + ``bleach.clean`` allowlist to the cover text."""
    if len(raw.encode("utf-8")) > _HOME_INTRO_MAX_BYTES:
        raise DomainValidationError(
            code="FILE_TOO_LARGE",
            message=(
                f"Cover text must be ≤ {_HOME_INTRO_MAX_BYTES // 1024} KB"
            ),
        )
    return bleach.clean(
        raw,
        tags=_HOME_INTRO_ALLOWED_TAGS,
        attributes=_HOME_INTRO_ALLOWED_ATTRS,
        protocols=_HOME_INTRO_ALLOWED_PROTOCOLS,
        strip=True,
    )


class HomeIntroBody(BaseModel):
    html: str


@router.put("/home-intro")
async def settings_home_intro_update(
    body: HomeIntroBody,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[dict[str, str]]:
    """Set or clear the public homepage intro HTML [Admin]."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.system_setting import SystemSetting

    cleaned = _sanitise_home_intro(body.html)
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == "home_intro_html"))
    if row is None:
        row = SystemSetting(key="home_intro_html", value=cleaned, type="string")
        db.add(row)
    else:
        row.value = cleaned
        row.updated_by = current_user.id
        row.updated_at = datetime.now(UTC)
    await db.flush()
    return DataResponse(data={"html": cleaned})


# ── Authenticated settings CRUD ────────────────────────────────────────────────

@router.get("")
async def settings_list(
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[SettingResponse]]:
    data = await list_settings(db)
    return DataResponse(data=data)


@router.get("/{key}")
async def setting_detail(
    key: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[SettingResponse]:
    data = await get_setting(db, key)
    return DataResponse(data=data)


@router.patch("/{key}")
async def setting_update(
    key: str,
    body: SettingUpdate,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[SettingResponse]:
    data = await update_setting(db, key, body, current_user)
    return DataResponse(data=data)
