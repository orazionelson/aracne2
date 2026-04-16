import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse

from app.middleware.rate_limiter import limiter
from sqlalchemy.ext.asyncio import AsyncSession

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
    content = await file.read()
    data = await upload_logo(db, content, file.filename or "logo.png", current_user)
    return DataResponse(data=data)


@router.get("/logo/file")
@limiter.limit("120/minute")
async def settings_logo_file(request: Request) -> FileResponse:
    """Serve the uploaded platform logo file (public, no authentication).

    Returns 404 if no custom logo has been uploaded yet; the frontend falls
    back to /aracne-logo.png in that case.
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
    content = await file.read()
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
