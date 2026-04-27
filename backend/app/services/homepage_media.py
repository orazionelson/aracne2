"""Homepage media library.

A single shared media folder for the public Pagine Pubbliche surface
— logo overrides, intro-text illustrations, anything an admin wants
to reference from `home_intro_html` without leaving the platform.

The folder lives at ``settings.media_dir / "homepage"``. Files are
served publicly at ``/api/v1/settings/homepage-media/<filename>``;
upload / list / delete are Admin-only.

Filename sanitisation, SVG scrubbing, allow-lists and the
``MediaFile`` dataclass are imported from
:mod:`app.services.website_media` so the two surfaces enforce
identical security rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog

from app.config import settings
from app.core.exceptions import DomainValidationError, NotFoundError
from app.services.website_media import (
    MediaFile,
    _MAX_UPLOAD_BYTES,
    _sanitize_svg,
    guess_content_type,
    sanitize_filename,
)

logger = structlog.get_logger()


def media_dir() -> Path:
    """Return the homepage media directory (created on demand)."""
    d = settings.media_dir / "homepage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_media() -> list[MediaFile]:
    d = media_dir()
    out: list[MediaFile] = []
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        stat = p.stat()
        out.append(
            MediaFile(
                filename=p.name,
                size_bytes=stat.st_size,
                content_type=guess_content_type(p.name),
                uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )
    return out


def save_media(filename: str, payload: bytes) -> MediaFile:
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise DomainValidationError(
            code="FILE_TOO_LARGE",
            message=(
                f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
            ),
        )
    safe_name = sanitize_filename(filename)
    d = media_dir()
    path = d / safe_name
    resolved = path.resolve()
    if not resolved.is_relative_to(d.resolve()):
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message="Filename resolves outside the homepage media folder",
        )
    if path.suffix == ".svg":
        payload = _sanitize_svg(payload)
    path.write_bytes(payload)
    stat = path.stat()
    logger.info("homepage_media_uploaded", filename=safe_name, size=stat.st_size)
    return MediaFile(
        filename=safe_name,
        size_bytes=stat.st_size,
        content_type=guess_content_type(safe_name),
        uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
    )


def delete_media(filename: str) -> None:
    safe_name = sanitize_filename(filename)
    path = media_dir() / safe_name
    if not path.exists() or not path.is_file():
        raise NotFoundError(f"Media file '{safe_name}' not found")
    path.unlink()
    logger.info("homepage_media_deleted", filename=safe_name)


def read_media(filename: str) -> tuple[bytes, str]:
    safe_name = sanitize_filename(filename)
    d = media_dir()
    path = d / safe_name
    resolved = path.resolve()
    if not resolved.is_relative_to(d.resolve()):
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message="Filename resolves outside the homepage media folder",
        )
    if not path.exists() or not path.is_file():
        raise NotFoundError(f"Media file '{safe_name}' not found")
    return path.read_bytes(), guess_content_type(safe_name)
