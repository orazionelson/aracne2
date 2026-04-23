"""Help plugin — Markdown rendering, navigation tree, search, asset serving.

All functions resolve paths against ``settings.help_docs_root`` and
refuse to follow anything outside that tree. The in-process cache keeps
``(mtime_ns, title, html, plaintext)`` per page so repeat requests skip
both the filesystem read and the Markdown pass.
"""

from __future__ import annotations

import re
from pathlib import Path

import bleach
from markdown_it import MarkdownIt

from app.config import settings
from app.plugins.help.schemas import HelpPage, HelpSearchHit, HelpTreeNode

# ── Markdown renderer ────────────────────────────────────────────────

_md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
_md.enable(["table", "strikethrough"])

# HTML sanitiser whitelist — broad enough for docs, tight enough to
# block script injection even if a .md file sneaks in raw HTML.
_ALLOWED_TAGS: set[str] = {
    "a", "abbr", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "img", "li", "ol", "p", "pre", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul", "del", "s",
}
_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "*": ["class", "id"],
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
}
_ALLOWED_PROTOCOLS: list[str] = ["http", "https", "mailto"]

# ── Asset serving ────────────────────────────────────────────────────

_ASSET_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
_ASSET_CONTENT_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# ── Page cache ───────────────────────────────────────────────────────

# Keyed by normalised path (no leading slash, no .md). Value is
# (mtime_ns, title, html, plaintext).
_page_cache: dict[str, tuple[int, str, str, str]] = {}


# ── Path helpers ─────────────────────────────────────────────────────


def _root() -> Path:
    return settings.help_docs_root.resolve()


def _resolve_page_file(path: str) -> Path | None:
    """Return the on-disk ``.md`` file for a requested page path, or None.

    Accepts the logical path used by the frontend (``01-basics/02-roles``)
    and maps it to ``<root>/01-basics/02-roles.md`` after resolving
    symlinks and verifying the target stays inside ``help_docs_root``.
    Empty path maps to ``<root>/index.md``.
    """
    root = _root()
    rel = (path or "").strip().strip("/")
    # Empty → index.md at root; explicit "index" too.
    if not rel or rel == "index":
        candidate = root / "index.md"
    elif rel.endswith("/"):
        candidate = root / rel.rstrip("/") / "index.md"
    else:
        candidate = root / f"{rel}.md"
        if not candidate.is_file():
            # Fallback: treat as a directory with an index.md.
            alt = root / rel / "index.md"
            if alt.is_file():
                candidate = alt
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    if not _is_inside(resolved, root) or not resolved.is_file():
        return None
    return resolved


def _resolve_asset_file(path: str) -> Path | None:
    """Return the on-disk asset file for a request, or None if disallowed."""
    root = _root()
    rel = (path or "").strip().strip("/")
    if not rel:
        return None
    candidate = root / rel
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    if not _is_inside(resolved, root) or not resolved.is_file():
        return None
    if resolved.suffix.lower() not in _ASSET_EXTENSIONS:
        return None
    return resolved


def _is_inside(child: Path, parent: Path) -> bool:
    """Check whether ``child`` is contained in ``parent`` after resolution."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def asset_content_type(file: Path) -> str:
    return _ASSET_CONTENT_TYPES.get(file.suffix.lower(), "application/octet-stream")


# ── Rendering ────────────────────────────────────────────────────────


_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


def _first_heading(text: str, fallback: str) -> str:
    m = _H1_RE.search(text)
    if not m:
        return fallback
    return m.group(1).strip()


def _rewrite_asset_urls(html: str) -> str:
    """Route relative ``<img>`` srcs through the plugin asset endpoint.

    Accepts anything that does not already have a scheme; leading ``./``
    and ``../`` are collapsed by the server at request time, so only
    the prefix is rewritten here.
    """

    def _sub(match: re.Match[str]) -> str:
        quote = match.group(1)
        url = match.group(2)
        if re.match(r"^[a-z][a-z0-9+.\-]*:", url, re.IGNORECASE) or url.startswith("/"):
            return match.group(0)
        # Strip any leading "./" and "../" segments; we serve assets via
        # a flat namespace rooted at help_docs_root.
        cleaned = re.sub(r"^(\.\./|\./)+", "", url)
        return f'src={quote}/api/v1/plugins/help/assets/{cleaned}{quote}'

    return re.sub(r"src=([\"'])([^\"']+)\1", _sub, html)


def _plaintext(html: str) -> str:
    """Strip HTML tags for the search index and snippet generation."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _render_from_markdown(source: str) -> tuple[str, str]:
    """Return (sanitised_html, plaintext) for a Markdown string."""
    rendered = _md.render(source)
    rendered = _rewrite_asset_urls(rendered)
    safe = bleach.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return safe, _plaintext(safe)


def _cached_render(file: Path, logical_path: str) -> tuple[str, str, str]:
    """Return (title, html, plaintext), rendering from disk when stale."""
    mtime_ns = file.stat().st_mtime_ns
    cached = _page_cache.get(logical_path)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1], cached[2], cached[3]
    source = file.read_text(encoding="utf-8")
    title = _first_heading(source, _humanise(file.stem))
    html, plaintext = _render_from_markdown(source)
    _page_cache[logical_path] = (mtime_ns, title, html, plaintext)
    return title, html, plaintext


def reset_cache() -> None:
    """Drop every cached render — used by tests and the explicit refresh."""
    _page_cache.clear()


# ── Navigation tree ──────────────────────────────────────────────────


_PREFIX_RE = re.compile(r"^\d+[-_]")


def _humanise(slug: str) -> str:
    """Turn ``01-basics`` into ``Basics`` for a tree label fallback."""
    stripped = _PREFIX_RE.sub("", slug)
    return stripped.replace("-", " ").replace("_", " ").strip().title() or slug


def _logical_path(file: Path) -> str:
    rel = file.resolve().relative_to(_root())
    s = str(rel).replace("\\", "/")
    return s[:-3] if s.endswith(".md") else s


def build_tree() -> list[HelpTreeNode]:
    """Walk ``help_docs_root`` and produce a sorted navigation tree.

    Directories become sections (``is_section=True``); ``.md`` files
    become pages. The root ``index.md`` is intentionally omitted — the
    frontend binds the root path separately as "Home".
    """
    root = _root()
    if not root.is_dir():
        return []
    return _walk(root, prefix="")


def _walk(directory: Path, *, prefix: str) -> list[HelpTreeNode]:
    nodes: list[HelpTreeNode] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    for entry in entries:
        name = entry.name
        if name.startswith(".") or name.startswith("_"):
            continue
        if entry.is_dir():
            children = _walk(entry, prefix=f"{prefix}{name}/")
            if not children:
                continue
            nodes.append(HelpTreeNode(
                path=f"{prefix}{name}".rstrip("/"),
                title=_directory_title(entry, _humanise(name)),
                is_section=True,
                children=children,
            ))
        elif entry.suffix == ".md":
            # index.md inside a subfolder is surfaced as the directory
            # landing page, not as a sibling page.
            if prefix and name == "index.md":
                continue
            if not prefix and name == "index.md":
                # Home page is bound separately by the frontend.
                continue
            path = _logical_path(entry)
            nodes.append(HelpTreeNode(
                path=path,
                title=_file_title(entry),
                is_section=False,
            ))
    return nodes


def _file_title(file: Path) -> str:
    try:
        source = file.read_text(encoding="utf-8")
    except OSError:
        return _humanise(file.stem)
    return _first_heading(source, _humanise(file.stem))


def _directory_title(directory: Path, fallback: str) -> str:
    """Prefer the index.md heading of a section for its tree label."""
    index = directory / "index.md"
    if index.is_file():
        try:
            return _first_heading(index.read_text(encoding="utf-8"), fallback)
        except OSError:
            return fallback
    return fallback


# ── Public API ───────────────────────────────────────────────────────


def get_page(path: str) -> HelpPage | None:
    file = _resolve_page_file(path)
    if file is None:
        return None
    logical = _logical_path(file)
    title, html, _ = _cached_render(file, logical)
    return HelpPage(
        path=logical,
        title=title,
        html=html,
        breadcrumb=_breadcrumb(logical, title),
    )


def _breadcrumb(logical_path: str, title: str) -> list[tuple[str, str]]:
    """Build breadcrumb entries — one per path segment, root excluded."""
    if not logical_path or logical_path == "index":
        return [("", title)]
    parts = logical_path.split("/")
    crumbs: list[tuple[str, str]] = [("", "Help")]
    accumulated: list[str] = []
    for part in parts[:-1]:
        accumulated.append(part)
        section_path = "/".join(accumulated)
        directory = _root() / section_path
        crumbs.append((section_path, _directory_title(directory, _humanise(part))))
    crumbs.append((logical_path, title))
    return crumbs


def search(q: str, *, limit: int = 20) -> list[HelpSearchHit]:
    """Run a case-insensitive substring search over every help page."""
    query = q.strip()
    if len(query) < 2:
        return []
    hits: list[HelpSearchHit] = []
    terms = [t for t in re.split(r"\s+", query) if t]
    for file in _root().rglob("*.md"):
        try:
            resolved = file.resolve()
        except OSError:
            continue
        if not _is_inside(resolved, _root()):
            continue
        logical = _logical_path(resolved)
        # Re-use the render cache to avoid re-parsing unchanged files.
        title, _html, plaintext = _cached_render(resolved, logical)
        haystack = plaintext.lower()
        if not all(t.lower() in haystack for t in terms):
            continue
        hits.append(HelpSearchHit(
            path=logical,
            title=title,
            snippet=_snippet(plaintext, terms),
        ))
        if len(hits) >= limit:
            break
    return hits


def _snippet(plaintext: str, terms: list[str], *, radius: int = 80) -> str:
    """Return ~160 chars of context around the first matching term.

    Matched terms are wrapped in ``<mark>``. The rest of the snippet is
    HTML-escaped defensively so the frontend can inject with v-html
    without a second pass.
    """
    if not plaintext or not terms:
        return ""
    low = plaintext.lower()
    first_pos = -1
    for term in terms:
        pos = low.find(term.lower())
        if pos >= 0 and (first_pos < 0 or pos < first_pos):
            first_pos = pos
    if first_pos < 0:
        return _escape(plaintext[: 2 * radius]) + ("…" if len(plaintext) > 2 * radius else "")
    start = max(0, first_pos - radius)
    end = min(len(plaintext), first_pos + radius)
    excerpt = plaintext[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(plaintext) else ""
    escaped = _escape(excerpt)
    for term in sorted(set(terms), key=len, reverse=True):
        pattern = re.compile(re.escape(_escape(term)), re.IGNORECASE)
        escaped = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)
    return f"{prefix}{escaped}{suffix}"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def get_asset(path: str) -> tuple[Path, str] | None:
    """Return (resolved_file, content_type) or None for a disallowed request."""
    file = _resolve_asset_file(path)
    if file is None:
        return None
    return file, asset_content_type(file)
