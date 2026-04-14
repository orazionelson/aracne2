"""Document media router — image upload and retrieval for TEI documents.

Each document has an isolated media directory on the filesystem:
  <documents_media_root>/<collection_slug>/<doc_filename>/

Endpoints
---------
GET    /collections/{slug}/documents/{doc_filename}/media
    List images for a document.  [E+]

POST   /collections/{slug}/documents/{doc_filename}/media
    Upload a new image.  [E+] — write access required (collection not published,
    actor is assigned editor or has collection permission, or EiC+).

DELETE /collections/{slug}/documents/{doc_filename}/media/{filename}
    Delete an image.  [E+] — same write-access rules as POST.

GET    /collections/{slug}/documents/{doc_filename}/media/{filename}
    Serve an image file.  [auth] — read access sufficient.
"""

import mimetypes
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.schemas.common import DataResponse
from app.schemas.media import MediaItem, MediaListResponse
from app.services import media as media_svc
from app.services.xmldb import (
    _assert_read_access,
    _assert_write_access,
    _audit,
    _get_or_404,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/collections", tags=["media"])

_DbDep = Annotated[AsyncSession, Depends(get_async_session)]
_EditorDep = Annotated[User, Depends(require_role(min_role="Editor"))]
_AuthDep = Annotated[User, Depends(require_role(min_role="User"))]

_DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # fallback if system_setting is missing


async def _get_max_bytes(db: AsyncSession) -> int:
    """Read media_max_upload_size_mb from system_settings (fallback: 50 MB)."""
    row = await db.get(SystemSetting, "media_max_upload_size_mb")
    if row:
        try:
            return int(row.value) * 1024 * 1024
        except ValueError:
            pass
    return _DEFAULT_MAX_BYTES


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/{slug}/documents/{doc_filename}/media")
async def list_document_media(
    slug: str,
    doc_filename: str,
    request: Request,
    current_user: _EditorDep,
    db: _DbDep,
) -> MediaListResponse:
    """List all images currently stored for a TEI document."""
    col = await _get_or_404(db, slug)
    await _assert_read_access(db, col, current_user, request.state.role)
    items = await media_svc.list_media(col.slug, doc_filename)
    return MediaListResponse(data=items)


@router.post("/{slug}/documents/{doc_filename}/media", status_code=201)
async def upload_document_media(
    slug: str,
    doc_filename: str,
    file: UploadFile,
    request: Request,
    current_user: _EditorDep,
    db: _DbDep,
) -> DataResponse[MediaItem]:
    """Upload an image for a TEI document.

    Allowed formats: JPEG, PNG, WebP, TIFF.
    Maximum size: configured via system_setting *media_max_upload_size_mb* (default 50 MB).
    """
    col = await _get_or_404(db, slug)
    _assert_write_access(col, current_user, request.state.role)
    max_bytes = await _get_max_bytes(db)
    item = await media_svc.save_media(col.slug, doc_filename, file, max_bytes)
    _audit(
        db,
        "media.uploaded",
        current_user,
        col,
        {"doc": doc_filename, "filename": item.filename, "size": item.size},
    )
    logger.info(
        "media_uploaded",
        collection=col.slug,
        doc=doc_filename,
        filename=item.filename,
        size=item.size,
        actor=current_user.username,
    )
    return DataResponse(data=item)


@router.delete(
    "/{slug}/documents/{doc_filename}/media/{filename}", status_code=204
)
async def delete_document_media(
    slug: str,
    doc_filename: str,
    filename: str,
    request: Request,
    current_user: _EditorDep,
    db: _DbDep,
) -> None:
    """Delete an image from a TEI document's media directory."""
    col = await _get_or_404(db, slug)
    _assert_write_access(col, current_user, request.state.role)
    await media_svc.delete_media(col.slug, doc_filename, filename)
    _audit(
        db,
        "media.deleted",
        current_user,
        col,
        {"doc": doc_filename, "filename": filename},
    )
    logger.info(
        "media_deleted",
        collection=col.slug,
        doc=doc_filename,
        filename=filename,
        actor=current_user.username,
    )


@router.get("/{slug}/documents/{doc_filename}/media/{filename}")
async def serve_document_media(
    slug: str,
    doc_filename: str,
    filename: str,
    request: Request,
    current_user: _AuthDep,
    db: _DbDep,
) -> FileResponse:
    """Serve a raw image file.

    Read access only — any authenticated user with collection read permission.
    """
    col = await _get_or_404(db, slug)
    await _assert_read_access(db, col, current_user, request.state.role)
    path = media_svc.get_media_path(col.slug, doc_filename, filename)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
