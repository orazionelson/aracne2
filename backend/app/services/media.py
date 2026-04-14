"""Document media service — filesystem operations for TEI document images.

Images for a document are stored at:
  <documents_media_root>/<collection_slug>/<doc_filename>/<image_file>

All public functions raise DomainValidationError or NotFoundError on failure;
callers do not need to handle OSError.
"""

import re
import unicodedata
from pathlib import Path

from fastapi import UploadFile

from app.config import settings
from app.core.exceptions import DomainValidationError, NotFoundError
from app.schemas.media import MediaItem

# Imported here (not re-defined) to keep doc_filename validation consistent
# with the XML document layer.  Raises DomainValidationError on traversal
# patterns such as "..", ".", or any name that does not end with ".xml".
from app.services.xmldb import _validate_filename as _validate_doc_filename

# Allowed image formats.  TIFF is included for manuscript scans (common format
# from digitisation workflows).
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
)
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/tiff"}
)

# Extension → canonical MIME type map (mimetypes module is unreliable for webp/tiff).
_EXT_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

# Base URL prefix for media serve endpoint.
_URL_BASE = "/api/v1/collections"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _media_dir(collection_slug: str, doc_filename: str) -> Path:
    """Return the media directory path for a document (not guaranteed to exist)."""
    return settings.documents_media_root / collection_slug / doc_filename


def _assert_contained(path: Path) -> None:
    """Raise DomainValidationError if *path* escapes documents_media_root."""
    root = settings.documents_media_root.resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise DomainValidationError("INVALID_FILENAME", "Invalid filename")


def _mime_for(filename: str) -> str:
    """Return the canonical MIME type for a filename, validating the extension."""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise DomainValidationError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"Extension '{ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )
    return _EXT_TO_MIME[ext]


def _check_content_type(content_type: str | None) -> None:
    """Validate the Content-Type declared by the upload (best-effort)."""
    if not content_type:
        return  # absent header — extension check is the primary guard
    ct = content_type.split(";")[0].strip().lower()
    if ct and ct not in _ALLOWED_CONTENT_TYPES:
        raise DomainValidationError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"Content-Type '{ct}' is not allowed. "
            f"Allowed: {', '.join(sorted(_ALLOWED_CONTENT_TYPES))}",
        )


def _media_url(collection_slug: str, doc_filename: str, filename: str) -> str:
    return f"{_URL_BASE}/{collection_slug}/documents/{doc_filename}/media/{filename}"


# ── Public API ─────────────────────────────────────────────────────────────────

def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename.

    Steps applied in order:
    1. Normalise unicode → ASCII approximation.
    2. Extract the basename (strip any path components).
    3. Replace non-alphanumeric characters (excluding `.`, `-`, `_`) with `_`.
    4. Collapse consecutive underscores.
    5. Strip leading / trailing dots and underscores.

    Raises DomainValidationError if the result is empty.
    """
    # Unicode normalisation → ASCII
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")
    # Basename only — prevent any path component from leaking through
    filename = Path(filename).name
    # Safe characters: alphanumeric, dot, hyphen, underscore
    filename = re.sub(r"[^\w.\-]", "_", filename)
    filename = re.sub(r"_+", "_", filename)
    filename = filename.strip("._")
    if not filename:
        raise DomainValidationError(
            "INVALID_FILENAME", "Filename is empty after sanitization"
        )
    return filename


async def list_media(collection_slug: str, doc_filename: str) -> list[MediaItem]:
    """Return a sorted list of images in the document's media directory.

    Returns an empty list if the directory does not exist yet.
    """
    _validate_doc_filename(doc_filename)
    media_dir = _media_dir(collection_slug, doc_filename)
    _assert_contained(media_dir)
    if not media_dir.exists():
        return []
    items: list[MediaItem] = []
    for path in sorted(media_dir.iterdir()):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            continue
        items.append(
            MediaItem(
                filename=path.name,
                url=_media_url(collection_slug, doc_filename, path.name),
                size=path.stat().st_size,
                content_type=_EXT_TO_MIME[ext],
            )
        )
    return items


async def save_media(
    collection_slug: str,
    doc_filename: str,
    file: UploadFile,
    max_bytes: int,
) -> MediaItem:
    """Validate and persist an uploaded image; return its MediaItem.

    Validation order:
    1. Sanitize filename.
    2. Validate extension (MIME type derived from extension).
    3. Validate declared Content-Type (best-effort).
    4. Read up to max_bytes+1 to enforce the size limit.
    5. Containment check against documents_media_root.
    6. Resolve name collision by appending a counter suffix.
    7. Write to disk.
    """
    _validate_doc_filename(doc_filename)
    original_name = file.filename or "upload"
    safe_name = sanitize_filename(original_name)
    mime = _mime_for(safe_name)
    _check_content_type(file.content_type)

    # Read with size guard (read one extra byte to detect over-limit files).
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise DomainValidationError(
            "FILE_TOO_LARGE",
            f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)} MB",
        )

    media_dir = _media_dir(collection_slug, doc_filename)
    _assert_contained(media_dir / safe_name)

    # Resolve name collision.
    dest = media_dir / safe_name
    if dest.exists():
        stem = Path(safe_name).stem
        ext = Path(safe_name).suffix
        counter = 2
        while dest.exists():
            dest = media_dir / f"{stem}_{counter}{ext}"
            counter += 1

    media_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    return MediaItem(
        filename=dest.name,
        url=_media_url(collection_slug, doc_filename, dest.name),
        size=len(data),
        content_type=mime,
    )


async def delete_media(
    collection_slug: str, doc_filename: str, filename: str
) -> None:
    """Delete a media file.  Raises NotFoundError if the file does not exist.

    Removes the parent directory if it becomes empty after deletion.
    """
    _validate_doc_filename(doc_filename)
    safe_name = sanitize_filename(filename)
    media_dir = _media_dir(collection_slug, doc_filename)
    dest = media_dir / safe_name
    _assert_contained(dest)
    if not dest.exists() or not dest.is_file():
        raise NotFoundError(f"Media file '{filename}' not found")
    dest.unlink()
    # Best-effort cleanup: remove the directory if it is now empty.
    try:
        media_dir.rmdir()
    except OSError:
        pass  # Directory not empty — leave it


def get_media_path(
    collection_slug: str, doc_filename: str, filename: str
) -> Path:
    """Return the absolute filesystem path of a media file.

    Raises NotFoundError if the file does not exist.
    """
    _validate_doc_filename(doc_filename)
    safe_name = sanitize_filename(filename)
    media_dir = _media_dir(collection_slug, doc_filename)
    dest = media_dir / safe_name
    _assert_contained(dest)
    if not dest.exists() or not dest.is_file():
        raise NotFoundError(f"Media file '{filename}' not found")
    return dest
