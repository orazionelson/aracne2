"""Per-website media library.

Each website has a dedicated ``media/`` folder living under
``settings.media_dir / "websites" / <slug>/`` (outside
``websites_root`` so files survive the wipe-and-rebuild of STATIC
sites). Designers upload images here preemptively — logo, cover,
illustrations for free pages — and then pick from the library via
the ``MediaPicker`` UI when filling the theme form, the homepage
columns, or a Markdown / WYSIWYG editor.

References in stored content travel as the stable pseudo-URL
``media://filename.png`` so the storage is **mode-agnostic**:

* DYNAMIC / HYBRID rendering: ``_rewrite_media_refs`` translates
  ``media://`` → ``/api/v1/websites/<slug>/media/<filename>`` at
  render time.
* STATIC build: the same rewriter — in ``"static"`` mode — emits a
  relative path ``media/<filename>`` and reports back the set of
  referenced filenames so the builder can copy only those into
  ``site_dir/media/``. Side-effect: the statically built tree stays
  self-contained; no runtime coupling.

Security:

* Filename is sanitised (lowercase alnum + dashes + a whitelisted
  extension); no path traversal reaches the filesystem.
* Allowed extensions: the image types listed in ``_ALLOWED_EXT``.
* SVG uploads are accepted but scrubbed through ``_sanitize_svg``:
  scripts, event handlers, external references, and foreign
  elements are stripped before the file is written to disk. Anything
  left is a static drawing — safe to inline or link.
* Max file size is 8 MB by default (hardcoded for the MVP).
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import defusedxml.ElementTree as DET
import structlog

from app.config import settings
from app.core.exceptions import DomainValidationError, NotFoundError

logger = structlog.get_logger()


# ── Limits / allow-lists ─────────────────────────────────────────────────────

_ALLOWED_EXT: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"}
)
_MAX_UPLOAD_BYTES: int = 8 * 1024 * 1024  # 8 MB
_MAX_FILENAME_LEN: int = 128


@dataclass(frozen=True, slots=True)
class MediaFile:
    """One file in a website's media folder — enough for the admin list."""

    filename: str
    size_bytes: int
    content_type: str
    uploaded_at: datetime


# ── Path helpers ─────────────────────────────────────────────────────────────


def _media_root() -> Path:
    return settings.media_dir / "websites"


def media_dir_for(slug: str) -> Path:
    """Return the per-website media directory (created on demand)."""
    # ``slug`` itself is validated upstream on website creation; the join
    # below still constrains the result under the root just in case.
    root = _media_root()
    d = root / slug
    resolved = d.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise DomainValidationError(
            code="INVALID_SLUG",
            message="Website slug resolves outside the media root",
        )
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Filename sanitisation ────────────────────────────────────────────────────


_SAFE_CHARS = re.compile(r"[^a-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """Return a safe, case-normalised filename; raise on empty / bad ext.

    Strips directory components, ASCII-folds, lowercases, collapses any
    non-``[a-z0-9._-]`` run to a single dash. A final validation check
    refuses empty basenames, leading dots, and unknown extensions.
    """
    if not name:
        raise DomainValidationError(
            code="INVALID_FILENAME", message="Filename is empty"
        )
    # Strip any directory the client accidentally sent.
    bare = Path(name).name
    # NFKD-fold accented characters to their ASCII base then drop combining marks.
    normalised = (
        unicodedata.normalize("NFKD", bare)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    lowered = normalised.lower().strip()
    cleaned = _SAFE_CHARS.sub("-", lowered).strip("-.")
    if not cleaned:
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message="Filename must contain at least one alphanumeric character",
        )
    if len(cleaned) > _MAX_FILENAME_LEN:
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message=f"Filename exceeds {_MAX_FILENAME_LEN} characters",
        )
    suffix = Path(cleaned).suffix
    if suffix not in _ALLOWED_EXT:
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message=f"File extension '{suffix}' is not allowed. "
            f"Allowed: {', '.join(sorted(_ALLOWED_EXT))}",
        )
    if cleaned.startswith("."):
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message="Filename cannot start with a dot",
        )
    return cleaned


_CONTENT_TYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}


def guess_content_type(filename: str) -> str:
    return _CONTENT_TYPE.get(Path(filename).suffix.lower(), "application/octet-stream")


# ── SVG sanitisation ─────────────────────────────────────────────────────────


_SVG_FORBIDDEN_TAGS = {
    # Scripting.
    "script", "handler",
    # Foreign content that can host scripts.
    "foreignObject",
    # Embeds that can fetch remote resources with active behaviour.
    "iframe", "video", "audio", "use",  # <use> can pull xlink:href=javascript:
}
# Attributes that can smuggle executable content.
_SVG_FORBIDDEN_ATTR_PREFIXES = ("on",)  # onclick, onload, onmouseover…
_SVG_FORBIDDEN_ATTR_EXACT = {"xlink:href", "href"}  # only when pointing at js:/data:


def _sanitize_svg(raw: bytes) -> bytes:
    """Strip scripting and external references from an SVG document.

    Uses ``defusedxml`` so the parse itself cannot resolve external
    entities. Then walks the tree removing:

    * any element whose (local) tag matches ``_SVG_FORBIDDEN_TAGS``;
    * any attribute starting with ``on`` (event handlers);
    * any ``href`` / ``xlink:href`` whose value begins with
      ``javascript:`` or ``data:`` (the two schemes that smuggle code).

    Returns serialised bytes of the cleaned tree. On parse failure the
    upload is rejected — garbled SVG is not worth ingesting.
    """
    try:
        tree = DET.fromstring(raw)
    except Exception as exc:
        raise DomainValidationError(
            code="INVALID_SVG",
            message=f"SVG could not be parsed: {exc}",
        ) from exc

    # ElementTree from defusedxml hands back a standard-library Element.
    # Walk it and mutate in place.

    def _strip(el: object) -> None:
        # Remove forbidden child elements first (so the tree shrinks).
        to_remove = []
        for child in list(getattr(el, "__iter__", lambda: [])()):
            local = getattr(child, "tag", "")
            if isinstance(local, str) and "}" in local:
                local = local.rsplit("}", 1)[1]
            if local in _SVG_FORBIDDEN_TAGS:
                to_remove.append(child)
        for c in to_remove:
            el.remove(c)  # type: ignore[attr-defined]
        # Strip forbidden attributes on *el*.
        attrib = getattr(el, "attrib", {})
        bad: list[str] = []
        for k, v in list(attrib.items()):
            local_k = k.rsplit("}", 1)[-1].lower()
            if any(local_k.startswith(p) for p in _SVG_FORBIDDEN_ATTR_PREFIXES):
                bad.append(k)
                continue
            if local_k in _SVG_FORBIDDEN_ATTR_EXACT:
                val = str(v).strip().lower()
                if val.startswith(("javascript:", "data:")):
                    bad.append(k)
        for k in bad:
            attrib.pop(k, None)
        # Recurse.
        for child in list(getattr(el, "__iter__", lambda: [])()):
            _strip(child)

    _strip(tree)

    import xml.etree.ElementTree as ET

    return ET.tostring(tree, encoding="utf-8", xml_declaration=True)


# ── CRUD ─────────────────────────────────────────────────────────────────────


def list_media(slug: str) -> list[MediaFile]:
    """List every file currently stored for *slug*, sorted by name."""
    d = media_dir_for(slug)
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


def save_media(slug: str, filename: str, payload: bytes) -> MediaFile:
    """Write *payload* as *filename* under the website's media folder.

    SVG input gets routed through :func:`_sanitize_svg` first. Non-SVG
    bytes are written verbatim — we do not re-encode images.
    """
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise DomainValidationError(
            code="FILE_TOO_LARGE",
            message=(
                f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
            ),
        )
    safe_name = sanitize_filename(filename)
    d = media_dir_for(slug)
    path = d / safe_name
    resolved = path.resolve()
    if not resolved.is_relative_to(d.resolve()):
        raise DomainValidationError(
            code="INVALID_FILENAME",
            message="Filename resolves outside the site's media folder",
        )

    if path.suffix == ".svg":
        payload = _sanitize_svg(payload)

    path.write_bytes(payload)
    stat = path.stat()
    logger.info(
        "website_media_uploaded",
        slug=slug,
        filename=safe_name,
        size=stat.st_size,
    )
    return MediaFile(
        filename=safe_name,
        size_bytes=stat.st_size,
        content_type=guess_content_type(safe_name),
        uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
    )


def delete_media(slug: str, filename: str) -> None:
    """Remove the file. 404 if it does not exist (so the admin UI gets an
    honest error if the user double-clicked Delete)."""
    safe_name = sanitize_filename(filename)
    path = media_dir_for(slug) / safe_name
    if not path.exists() or not path.is_file():
        raise NotFoundError(f"Media file '{safe_name}' not found")
    path.unlink()
    logger.info("website_media_deleted", slug=slug, filename=safe_name)


def read_media(slug: str, filename: str) -> tuple[bytes, str]:
    """Return ``(bytes, content_type)`` for a stored file or raise 404."""
    safe_name = sanitize_filename(filename)
    path = media_dir_for(slug) / safe_name
    resolved = path.resolve()
    if not resolved.is_relative_to(media_dir_for(slug).resolve()):
        raise NotFoundError("Media file not found")
    if not path.exists() or not path.is_file():
        raise NotFoundError(f"Media file '{safe_name}' not found")
    return path.read_bytes(), guess_content_type(safe_name)


# ── URL rewriting (media://... → runtime URL or static relative path) ────────


# Strict pattern: only filenames the upload pipeline accepts. Matches
# ``media://`` followed by our sanitised-filename charset, right up to
# the ``"`` / ``'`` / whitespace / ``)`` terminator that would close an
# ``src`` / ``href`` / ``url(...)`` / Markdown ``![](…)``.
_MEDIA_REF_RE = re.compile(r"media://([a-z0-9][a-z0-9._-]*)")


def rewrite_media_refs(
    html: str,
    slug: str,
    *,
    mode: str,
    collected: set[str] | None = None,
    static_prefix: str = "media/",
) -> str:
    """Replace every ``media://filename`` occurrence with a real URL.

    ``mode`` is ``"dynamic"`` (API URL) or ``"static"`` (relative path).

    In STATIC mode the emitted URL is ``{static_prefix}{name}``. The
    default prefix ``"media/"`` is correct for pages sitting at the
    root of the built tree (``site_dir/index.html``,
    ``site_dir/browse.html``). Pages written one level deep
    (``site_dir/pages/{s}.html``, ``site_dir/docs/{f}.html``) must
    pass ``static_prefix="../media/"`` so the relative URL resolves
    back up to ``site_dir/media/``.

    When *collected* is passed, matched filenames are inserted so the
    STATIC builder can copy only the files actually referenced —
    avoiding the "dump every byte into the ZIP" trap.
    """
    if "media://" not in html:
        return html

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if collected is not None:
            collected.add(name)
        if mode == "static":
            return f"{static_prefix}{name}"
        # DYNAMIC (and HYBRID, which mounts the same runtime API)
        # resolves through the absolute API URL — the page location
        # does not matter.
        return f"/api/v1/websites/{slug}/media/{name}"

    return _MEDIA_REF_RE.sub(_sub, html)


def copy_referenced_media_to_build(
    slug: str, site_dir: Path, filenames: set[str]
) -> None:
    """Copy the selected files from the site's media folder into
    ``site_dir/media/``. Missing files are logged but do not crash the
    build — a content reference that points at a deleted file renders as
    a broken image, and that is the right failure mode for the author
    to notice."""
    if not filenames:
        return
    src_dir = media_dir_for(slug)
    dst_dir = site_dir / "media"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        src = src_dir / name
        if not src.exists() or not src.is_file():
            logger.warning(
                "website_media_referenced_file_missing", slug=slug, filename=name
            )
            continue
        shutil.copy2(src, dst_dir / name)
