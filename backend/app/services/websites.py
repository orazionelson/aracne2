"""Website service — CRUD operations and Option A static site builder.

The static builder generates a self-contained folder of HTML/CSS files at
``settings.websites_root / slug /``.  Build and Dynamic/Hybrid render paths
diverge here; the data model (Website, WebsitePage) is shared by all three.
"""

from __future__ import annotations

import asyncio
import html as _html
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import structlog
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal
from app.models.collection import Collection, CollectionStatus
from app.models.collection_permission import CollectionPermission
from app.models.role import Role, RoleName, UserRole
from app.models.user import User
from app.models.website import BuildStatus, RenderingMode, Website, WebsitePage
from app.schemas.websites import (
    MetaSuggestionsResponse,
    WebsiteCreate,
    WebsitePageCreate,
    WebsitePageUpdate,
    WebsiteUpdate,
)

logger = structlog.get_logger()


# ── XSLT cache (same pattern as public_view.py) ───────────────────────────────

_XSLT_PATH = Path(__file__).parent.parent / "xslt" / "tei_generic.xsl"
_xslt_transform: etree.XSLT | None = None


def _get_transform() -> etree.XSLT:
    global _xslt_transform
    if _xslt_transform is None:
        xslt_doc = etree.parse(str(_XSLT_PATH))
        _xslt_transform = etree.XSLT(xslt_doc)
    return _xslt_transform


# ── HTML generation helpers ───────────────────────────────────────────────────

# Static CSS injected into every generated page.
# Theme colours are injected as :root custom properties in the <style> block.
_STATIC_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font);
  color: var(--text);
  background: var(--bg);
  line-height: 1.7;
  font-size: 1rem;
}
/* ── Navbar ── */
header { background: var(--primary); padding: 0 1.5rem; }
nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 960px;
  margin: 0 auto;
  height: 3.5rem;
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  color: #fff;
  text-decoration: none;
  font-weight: bold;
  font-size: 1.05rem;
}
.nav-logo {
  height: 2rem;
  width: auto;
  object-fit: contain;
  display: block;
}
.nav-links { display: flex; gap: 1.5rem; align-items: center; }
.nav-links a { color: rgba(255,255,255,0.82); text-decoration: none; font-size: 0.875rem; }
.nav-links a:hover { color: #fff; }
/* ── Hero (cover/index page) ── */
.hero { padding: 4.5rem 0 3.5rem; text-align: center; }
.hero h1 { font-size: 2.5rem; line-height: 1.15; margin-bottom: 1rem; }
.hero .lead {
  font-size: 1.1rem;
  color: #4b5563;
  max-width: 640px;
  margin: 0 auto 1rem;
}
.hero .meta-block { font-size: 0.875rem; color: #6b7280; margin-bottom: 2rem; }
.btn-primary {
  display: inline-block;
  background: var(--primary);
  color: #fff !important;
  padding: 0.7rem 1.75rem;
  border-radius: 0.375rem;
  text-decoration: none;
  font-size: 0.9rem;
  font-family: system-ui, sans-serif;
  letter-spacing: 0.01em;
}
.btn-primary:hover { opacity: 0.88; }
/* ── Home body grid ── */
.home-body { margin-top: 2.5rem; }
.home-grid { display: grid; gap: 2rem; }
.home-grid.layout-single  { grid-template-columns: 1fr; }
.home-grid.layout-two-left  { grid-template-columns: 30fr 70fr; }
.home-grid.layout-two-right { grid-template-columns: 70fr 30fr; }
.home-grid.layout-three  { grid-template-columns: 20fr 60fr 20fr; }
@media (max-width: 640px) { .home-grid { grid-template-columns: 1fr !important; } }
.home-col { min-width: 0; }
.home-col img { max-width: 100%; height: auto; display: block; margin: 1rem 0; border-radius: 0.25rem; }
.home-col a { color: var(--primary); }
.home-col h2 { font-size: 1.25rem; margin: 1.5rem 0 0.5rem; line-height: 1.2; }
.home-col h3 { font-size: 1.05rem; margin: 1.25rem 0 0.4rem; }
.home-col h4 { font-size: 0.95rem; margin: 1rem 0 0.3rem; }
.home-col p  { margin-bottom: 0.9rem; }
.home-col ul { margin: 0.5rem 0 0.9rem 1.25rem; }
.home-col ol { margin: 0.5rem 0 0.9rem 1.25rem; }
.home-col li { margin-bottom: 0.2rem; }
.home-col figure { margin: 1.25rem 0; }
.home-col figcaption { font-size: 0.8rem; color: #6b7280; margin-top: 0.35rem; text-align: center; }
/* ── Content pages ── */
main { max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem; }
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; line-height: 1.2; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.75rem; }
h3 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; }
p { margin-bottom: 1rem; }
a { color: var(--primary); }
ul { margin: 0.5rem 0 1rem 1.5rem; }
li { margin-bottom: 0.3rem; }
.doc-count { font-size: 0.85rem; color: #6b7280; margin-bottom: 1.5rem; }
.doc-list { list-style: none; margin-left: 0; }
.doc-list li { border-bottom: 1px solid #e5e7eb; padding: 0.75rem 0; }
.doc-list a { font-weight: 500; }
.doc-meta { font-size: 0.85rem; color: #6b7280; margin-top: 0.2rem; }
/* ── Document page — TEI header banner ── */
.tei-header {
  background: var(--doc-banner-bg);
  color: var(--doc-banner-text);
  padding: 1.5rem 1.5rem 1.25rem;
  margin-bottom: 2rem;
  border-radius: 0.375rem;
}
.tei-header .tei-title,
.tei-header .tei-author,
.tei-header .tei-pub { color: var(--doc-banner-text); }
.tei-header .tei-author { opacity: 0.85; font-style: italic; font-size: 0.95rem; margin-top: 0.3rem; }
.tei-header .tei-pub { opacity: 0.7; font-size: 0.8rem; margin-top: 0.2rem; }
.tei-body { padding-top: 0.5rem; }
footer {
  margin-top: 4rem;
  border-top: 1px solid #e5e7eb;
  padding: 1rem 1.5rem;
  text-align: center;
  font-size: 0.78rem;
  color: var(--footer-text);
  background: var(--footer-bg);
}
footer a { color: inherit; text-decoration: underline; }
footer a:hover { opacity: 0.75; }
/* ── Column page-menu widget ── */
.col-page-menu { margin: 0.75rem 0; }
.col-page-menu ul { list-style: none; margin: 0; padding: 0; }
.col-page-menu li { border-bottom: 1px solid #f3f4f6; }
.col-page-menu li:last-child { border-bottom: none; }
.col-page-menu a { display: block; padding: 0.4rem 0.5rem; color: var(--primary); text-decoration: none; font-size: 0.9rem; }
.col-page-menu a:hover { text-decoration: underline; }
/* ── Column search widget ── */
.col-search-widget { margin: 0.75rem 0; }
.col-search-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1.5px solid var(--primary);
  border-radius: 0.375rem;
  font-size: 0.9rem;
  font-family: inherit;
  outline: none;
  color: var(--text);
  background: #fff;
}
.col-search-input:focus { box-shadow: 0 0 0 2px rgba(99,102,241,0.12); }
.col-search-results {
  list-style: none;
  margin: 0.35rem 0 0;
  padding: 0;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
}
.col-search-results li { border-bottom: 1px solid #f3f4f6; }
.col-search-results li:last-child { border-bottom: none; }
.col-search-results a {
  display: block;
  padding: 0.4rem 0.75rem;
  font-size: 0.85rem;
  color: var(--text);
  text-decoration: none;
}
.col-search-results a:hover { background: #f9fafb; color: var(--primary); }
/* ── Search page ── */
.search-wrap { max-width: 720px; margin: 0 auto; padding: 2rem 1rem; }
.search-wrap h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 1.25rem; }
.search-box input[type=search] {
  width: 100%;
  padding: 0.625rem 1rem;
  font-size: 1rem;
  font-family: inherit;
  border: 2px solid #d1d5db;
  border-radius: 0.5rem;
  outline: none;
  background: #fff;
  color: #1e293b;
}
.search-box input[type=search]:focus { border-color: var(--primary); }
.search-count { font-size: 0.8rem; color: #9ca3af; margin: 0.75rem 0 0.25rem; }
.search-hit {
  padding: 0.75rem 0;
  border-bottom: 1px solid #e5e7eb;
}
.search-hit a {
  font-size: 1rem;
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}
.search-hit a:hover { text-decoration: underline; }
.search-hit .hit-author { font-size: 0.8rem; color: #6b7280; margin-top: 0.15rem; }
.search-empty { color: #9ca3af; font-style: italic; margin-top: 1rem; }
"""


_DEFAULT_FONT = 'Georgia,"Times New Roman",serif'


def _style_block(theme: dict) -> str:
    primary = _html.escape(theme.get("primary_color", "#1e293b"))
    text = _html.escape(theme.get("text_color", "#1e293b"))
    bg = _html.escape(theme.get("bg_color", "#ffffff"))
    # Banner defaults: same primary as navbar background, white text for contrast
    doc_banner_bg = _html.escape(theme.get("doc_banner_bg", primary))
    doc_banner_text = _html.escape(theme.get("doc_banner_text", "#ffffff"))
    # Font family — sanitize to strip HTML injection chars but keep CSS syntax intact
    font = re.sub(r"[<>&]", "", theme.get("font_family", _DEFAULT_FONT) or _DEFAULT_FONT)
    # Footer colours — fall back to current hard-coded defaults when unset
    footer_bg = _html.escape(theme.get("footer_bg", "transparent") or "transparent")
    footer_color = _html.escape(theme.get("footer_text", "#9ca3af") or "#9ca3af")
    root_vars = (
        f":root{{--primary:{primary};--text:{text};--bg:{bg};"
        f"--doc-banner-bg:{doc_banner_bg};--doc-banner-text:{doc_banner_text};"
        f"--font:{font};--footer-bg:{footer_bg};--footer-text:{footer_color};}}"
    )
    return f"<style>\n{root_vars}\n{_STATIC_CSS}\n</style>"


# Sentinels emitted by widget Tiptap nodes (renderHTML output).
_WIDGET_TAG_SEARCH_BAR = '<div data-widget="search-bar"></div>'
_WIDGET_TAG_PAGE_MENU  = '<div data-widget="page-menu"></div>'


def _build_search_widget_html() -> str:
    """Return HTML+JS for the inline search-bar column widget.

    The widget fetches search.json (expected at the root of the static site,
    i.e. next to index.html) and filters results in real time.  Intended for
    home-page columns only — paths are relative to index.html.
    """
    js = (
        "(function(){"
        "var idx=null;"
        "function f(inp){"
        "var q=inp.value,lst=inp.nextElementSibling;"
        "if(!q.trim()){lst.hidden=true;return;}"
        "if(idx===null){"
        "fetch('search.json')"
        ".then(function(r){return r.json();})"
        ".then(function(d){idx=d;f(inp);})"
        ".catch(function(){idx=[];});"
        "return;}"
        "var hits=idx.filter(function(i){"
        "return(i.title+' '+(i.author||'')).toLowerCase()"
        ".indexOf(q.toLowerCase())>=0;"
        "}).slice(0,8);"
        "lst.innerHTML=hits.map(function(h){"
        "return'<li><a href=\"docs/'+h.filename+'.html\">'+(h.title||h.filename)+'</a></li>';"
        "}).join('');"
        "lst.hidden=hits.length===0;}"
        "window.colSearchFilter=window.colSearchFilter||f;"
        "})();"
    )
    return (
        '<div class="col-search-widget">'
        '<input type="search" class="col-search-input"'
        ' placeholder="Search documents\u2026"'
        ' oninput="colSearchFilter(this)"'
        ' aria-label="Search documents" />'
        '<ul class="col-search-results" hidden></ul>'
        "</div>"
        f"<script>{js}</script>"
    )


def _build_page_menu_html(pages: list[WebsitePage]) -> str:
    """Return HTML for the page-menu column widget.

    Renders a simple nav list of links to all visible free pages.
    Paths are relative to the site root (index.html lives there).
    Returns an empty string when there are no visible pages.
    """
    if not pages:
        return ""
    items = "".join(
        f'<li><a href="pages/{_html.escape(p.slug)}.html">{_html.escape(p.title)}</a></li>'
        for p in pages
    )
    return f'<nav class="col-page-menu"><ul>{items}</ul></nav>'


def _render_col_content(text: str, pages: list[WebsitePage] | None = None) -> str:
    """Return column body HTML for embedding in the static page.

    If *text* looks like HTML (starts with a tag — Tiptap output) it is
    returned as-is after expanding any widget placeholders.  Otherwise it is
    treated as lightweight Markdown so that content written before the WYSIWYG
    editor was introduced still renders correctly.

    Both paths are trusted Designer+ input written for their own static site;
    no html.escape is applied.
    """
    stripped = text.strip()
    if not stripped:
        return ""
    # HTML passthrough: Tiptap always produces output starting with a tag.
    if stripped.startswith("<"):
        result = stripped.replace(_WIDGET_TAG_SEARCH_BAR, _build_search_widget_html())
        result = result.replace(_WIDGET_TAG_PAGE_MENU, _build_page_menu_html(pages or []))
        return result
    # Markdown fallback (legacy / plain-text content)
    return _md_col_to_html(stripped)


def _md_col_to_html(text: str) -> str:
    """Lightweight Markdown → HTML for column content (legacy/fallback path)."""
    import re as _re

    def inline(s: str) -> str:
        s = _re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">',
            s,
        )
        s = _re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
            s,
        )
        s = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        s = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', s)
        return s

    lines = text.splitlines()
    blocks: list[str] = []
    para_lines: list[str] = []

    def flush() -> None:
        if para_lines:
            blocks.append(f"<p>{' '.join(inline(l) for l in para_lines)}</p>")
            para_lines.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("### "):
            flush(); blocks.append(f"<h4>{inline(s[4:])}</h4>")
        elif s.startswith("## "):
            flush(); blocks.append(f"<h3>{inline(s[3:])}</h3>")
        elif s.startswith("# "):
            flush(); blocks.append(f"<h2>{inline(s[2:])}</h2>")
        elif s.startswith("<"):
            flush(); blocks.append(s)
        else:
            para_lines.append(s)

    flush()
    return "\n".join(blocks)


def _parse_aracne_nav(nav_config: list) -> list[dict]:
    """Return the ordered Aracne system-page descriptors from *nav_config*.

    Fills in defaults for any missing entry so the caller always receives
    exactly three records: home (always first), then browse and search sorted
    by their stored ``sort_order``.
    """
    _defaults: dict[str, dict] = {
        "home":   {"id": "home",   "sort_order": 0, "is_hidden": False},
        "browse": {"id": "browse", "sort_order": 1, "is_hidden": False},
        "search": {"id": "search", "sort_order": 2, "is_hidden": False},
    }
    merged: dict[str, dict] = {}
    for page_id, default in _defaults.items():
        saved = next((p for p in nav_config if isinstance(p, dict) and p.get("id") == page_id), None)
        merged[page_id] = {**default, **(saved or {})}

    rest = sorted(
        [merged["browse"], merged["search"]],
        key=lambda p: p["sort_order"],
    )
    return [merged["home"], *rest]


def _render_navbar(
    *,
    site_title: str,
    logo_url: str | None,
    pages: list[WebsitePage],
    path_prefix: str = "",
    nav_config: list | None = None,
) -> str:
    """Build the <header><nav> block.

    path_prefix must be "" for root-level pages (index.html, browse.html)
    and "../" for pages in subdirectories (docs/, pages/).
    nav_config controls visibility and order of Browse / Search links.
    """
    logo_html = ""
    if logo_url:
        esc_logo = _html.escape(logo_url)
        logo_html = f'<img src="{esc_logo}" alt="" class="nav-logo">'

    home_href = f"{path_prefix}index.html"
    browse_href = f"{path_prefix}browse.html"
    search_href = f"{path_prefix}search.html"

    # Merge system links and free-page links into a single list sorted by the
    # global sort_order (system pages from nav_config, free pages from sort_order).
    nav_items: list[tuple[int, str]] = []

    for ap in _parse_aracne_nav(nav_config or []):
        if ap.get("is_hidden"):
            continue
        so = int(ap["sort_order"])
        pid = ap["id"]
        if pid == "home":
            nav_items.append((so, f'<a href="{path_prefix}index.html">Home</a>'))
        elif pid == "browse":
            nav_items.append((so, f'<a href="{path_prefix}browse.html">Browse</a>'))
        elif pid == "search":
            nav_items.append((so, f'<a href="{path_prefix}search.html">Search</a>'))

    for page in pages:  # already filtered for visibility
        href = f"{path_prefix}pages/{_html.escape(page.slug)}.html"
        nav_items.append((page.sort_order, f'<a href="{href}">{_html.escape(page.title)}</a>'))

    nav_items.sort(key=lambda x: x[0])
    links_html = "".join(link for _, link in nav_items)

    return f"""<header>
    <nav>
      <a class="brand" href="{home_href}">{logo_html}<span>{_html.escape(site_title)}</span></a>
      <div class="nav-links">
        {links_html}
      </div>
    </nav>
  </header>"""


def _emit_meta(lines: list[str], name: str, raw: str | list | None) -> None:
    """Append one ``<meta>`` tag per non-empty value.

    ``raw`` may be a plain string or a list of strings (repeatable fields).
    """
    if raw is None:
        return
    values: list[str] = raw if isinstance(raw, list) else [raw]
    for item in values:
        v = str(item).strip()
        if v:
            lines.append(f'  <meta name="{name}" content="{_html.escape(v)}">')


def _build_meta_tags(meta: dict) -> str:
    """Build HTML <meta> tag strings from a meta_config dict.

    Standard HTML meta tags and Dublin Core (DC.*) are emitted only for
    non-empty values.  The DC namespace <link> is prepended automatically
    when at least one DC field has a value.  Repeatable fields may be stored
    as either a plain string or a list of strings.
    """
    if not meta:
        return ""

    lines: list[str] = []

    _html_fields = [
        ("keywords",    "keywords"),
        ("description", "description"),
        ("subject",     "subject"),
        ("copyright",   "copyright"),
        ("author",      "author"),
        ("designer",    "designer"),
        ("url",         "url"),
    ]
    for key, name in _html_fields:
        _emit_meta(lines, name, meta.get(key))

    _dc_fields = [
        ("dc_title",       "DC.Title"),
        ("dc_creator",     "DC.Creator"),
        ("dc_subject",     "DC.Subject"),
        ("dc_description", "DC.Description"),
        ("dc_publisher",   "DC.Publisher"),
        ("dc_contributor", "DC.Contributor"),
        ("dc_date",        "DC.Date"),
        ("dc_type",        "DC.Type"),
        ("dc_format",      "DC.Format"),
        ("dc_identifier",  "DC.Identifier"),
    ]
    dc_lines: list[str] = []
    for key, name in _dc_fields:
        _emit_meta(dc_lines, name, meta.get(key))
    if dc_lines:
        lines.append('  <link rel="schema.DC" href="http://purl.org/dc/elements/1.1/" />')
        lines.extend(dc_lines)

    return "\n".join(lines)


def _identifier_label(url: str) -> str:
    """Return a short human-readable label for a persistent identifier URL."""
    lower = url.lower()
    if "doi.org" in lower:
        return "DOI"
    if "hdl.handle.net" in lower or "handle.net" in lower:
        return "Handle"
    if "urn:" in lower:
        return "URN"
    return "Identifier"


def _render_page(
    *,
    site_title: str,
    page_title: str,
    content: str,
    style: str,
    navbar: str,
    footer_note: str = "",
    identifier_url: str = "",
    meta_tags: str = "",
) -> str:
    esc_site = _html.escape(site_title)
    esc_page = _html.escape(page_title)
    footer_extra = f'<span class="footer-publisher">{footer_note}</span> · ' if footer_note else ""
    if identifier_url:
        label = _identifier_label(identifier_url)
        esc_url = _html.escape(identifier_url)
        footer_extra += f'<a href="{esc_url}" class="footer-identifier" target="_blank" rel="noopener">{label}</a> · '
    meta_block = f"\n{meta_tags}" if meta_tags else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_page} — {esc_site}</title>{meta_block}
  {style}
</head>
<body>
  {navbar}
  <main>
    {content}
  </main>
  <footer>{footer_extra}Built with <a href="https://github.com/orazio-nelson/aracne2">Aracne2</a></footer>
</body>
</html>"""


def _md_to_html(content_md: str) -> str:
    """Convert page body to HTML.

    If the content starts with an HTML tag (Tiptap WYSIWYG output) it is
    returned as-is.  Otherwise the legacy Markdown path applies.
    """
    stripped = content_md.strip()
    if not stripped:
        return ""
    if stripped.startswith("<"):
        return stripped
    # Legacy Markdown
    lines = stripped.splitlines()
    blocks: list[str] = []
    para_lines: list[str] = []

    def flush_para() -> None:
        if para_lines:
            blocks.append(f"<p>{'<br>'.join(_html.escape(l) for l in para_lines)}</p>")
            para_lines.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush_para()
        elif s.startswith("### "):
            flush_para(); blocks.append(f"<h3>{_html.escape(s[4:])}</h3>")
        elif s.startswith("## "):
            flush_para(); blocks.append(f"<h2>{_html.escape(s[3:])}</h2>")
        elif s.startswith("# "):
            flush_para(); blocks.append(f"<h2>{_html.escape(s[2:])}</h2>")
        else:
            para_lines.append(s)

    flush_para()
    return "\n".join(blocks)


def _render_xml_to_html(xml_bytes: bytes) -> str:
    """Apply the generic TEI XSLT and return the <body> inner HTML."""
    transform = _get_transform()
    xml_doc = etree.fromstring(xml_bytes)  # noqa: S320 — from our own eXist-db
    result = transform(xml_doc)
    result_str = str(result)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", result_str, re.DOTALL | re.IGNORECASE)
    return body_match.group(1) if body_match else result_str


def _build_cover_content(
    *,
    website_title: str,
    col: Collection | None,
    doc_count: int,
    theme: dict,
    pages: list[WebsitePage] | None = None,
) -> str:
    """Return the hero/cover HTML for index.html.

    Publisher / year are intentionally omitted here — they appear in the footer.
    Below the hero, an optional column grid is rendered from theme_config keys:
      home_layout : "single" | "two_left" | "two_right" | "three"
      col_left    : body text for left sidebar column
      col_center  : body text for central column (shown in all layouts)
      col_right   : body text for right sidebar column
    """
    title = _html.escape(col.title if col else website_title)
    lead = ""
    if col and col.description:
        lead = f'<p class="lead">{_html.escape(col.description)}</p>'

    author_block = ""
    if col and col.author:
        author_block = f'<p class="meta-block">{_html.escape(col.author)}</p>'

    browse_label = f"Browse {doc_count} document{'s' if doc_count != 1 else ''} →"
    cta = f'<a href="browse.html" class="btn-primary">{browse_label}</a>'

    hero = f"""<div class="hero">
  <h1>{title}</h1>
  {lead}
  {author_block}
  {cta}
</div>"""

    # ── Column body grid ──────────────────────────────────────────────────
    layout = theme.get("home_layout", "single")
    center = _render_col_content(theme.get("col_center", "") or "", pages)
    left   = _render_col_content(theme.get("col_left", "") or "", pages)
    right  = _render_col_content(theme.get("col_right", "") or "", pages)

    if layout == "two_left":
        cols = (
            f'<div class="home-col">{left}</div>'
            f'<div class="home-col">{center}</div>'
        )
        css_class = "layout-two-left"
    elif layout == "two_right":
        cols = (
            f'<div class="home-col">{center}</div>'
            f'<div class="home-col">{right}</div>'
        )
        css_class = "layout-two-right"
    elif layout == "three":
        cols = (
            f'<div class="home-col">{left}</div>'
            f'<div class="home-col">{center}</div>'
            f'<div class="home-col">{right}</div>'
        )
        css_class = "layout-three"
    else:
        cols = f'<div class="home-col">{center}</div>'
        css_class = "layout-single"

    grid = ""
    if center or left or right:
        grid = f'<div class="home-body"><div class="home-grid {css_class}">{cols}</div></div>'

    return hero + grid


def _build_browse_content(docs: list[dict]) -> str:
    """Return the document list HTML for browse.html."""
    count = len(docs)
    items = ""
    for doc in docs:
        filename = _html.escape(doc["filename"])
        label = _html.escape(doc.get("title") or doc["filename"])
        author_line = (
            f'<div class="doc-meta">{_html.escape(doc["author"])}</div>'
            if doc.get("author")
            else ""
        )
        items += f'<li><a href="docs/{filename}.html">{label}</a>{author_line}</li>\n'

    return f"""<h1>Documents</h1>
<p class="doc-count">{count} document{'s' if count != 1 else ''}</p>
<ul class="doc-list">
{items}
</ul>"""


def _build_search_content() -> str:
    """Return the search page HTML with inline client-side search logic.

    The page fetches search.json (pre-built at site root) and filters results
    in real-time as the user types.  No external dependencies.
    """
    return """<div class="search-wrap">
  <h1>Search</h1>
  <div class="search-box">
    <input type="search" id="q" placeholder="Search documents…" autocomplete="off" autofocus>
  </div>
  <p class="search-count" id="count"></p>
  <div id="results"></div>
  <noscript>
    <p>JavaScript is required for search. <a href="browse.html">Browse all documents</a>.</p>
  </noscript>
</div>
<script>
(function () {
  var input   = document.getElementById('q');
  var results = document.getElementById('results');
  var countEl = document.getElementById('count');
  var index   = [];

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function render(q) {
    var term = q.trim().toLowerCase();
    var hits = term
      ? index.filter(function (d) {
          return d.title.toLowerCase().indexOf(term) !== -1 ||
                 d.author.toLowerCase().indexOf(term) !== -1;
        })
      : index;

    countEl.textContent = hits.length + ' result' + (hits.length !== 1 ? 's' : '');

    if (!hits.length) {
      results.innerHTML = '<p class="search-empty">No results found.</p>';
      return;
    }
    results.innerHTML = hits.map(function (d) {
      var authorLine = d.author
        ? '<div class="hit-author">' + esc(d.author) + '</div>'
        : '';
      return '<div class="search-hit"><a href="' + esc(d.url) + '">' +
             esc(d.title) + '</a>' + authorLine + '</div>';
    }).join('');
  }

  fetch('search.json')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      index = data;
      render(input.value);
    })
    .catch(function () {
      results.innerHTML = '<p class="search-empty">Search index not available.</p>';
    });

  input.addEventListener('input', function () { render(input.value); });
})();
</script>"""


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def _get_website(db: AsyncSession, slug: str) -> Website:
    row = await db.scalar(
        select(Website)
        .where(Website.slug == slug)
        .options(selectinload(Website.pages))
    )
    if row is None:
        raise NotFoundError(f"Website '{slug}' not found.")
    return row


async def list_websites(db: AsyncSession) -> list[Website]:
    result = await db.scalars(
        select(Website).options(selectinload(Website.pages)).order_by(Website.created_at.desc())
    )
    return list(result.all())


async def get_website(db: AsyncSession, slug: str) -> Website:
    return await _get_website(db, slug)


async def create_website(
    db: AsyncSession, data: WebsiteCreate, user_id: uuid.UUID
) -> Website:
    existing = await db.scalar(select(Website).where(Website.slug == data.slug))
    if existing is not None:
        raise ConflictError(f"Website with slug '{data.slug}' already exists.")

    website = Website(
        slug=data.slug,
        title=data.title,
        description=data.description,
        collection_id=data.collection_id,
        rendering_mode=data.rendering_mode,
        theme_config=data.theme_config,
        meta_config=data.meta_config,
        nav_config=data.nav_config,
        xslt_schema_id=data.xslt_schema_id,
        is_published=data.is_published,
        created_by=user_id,
    )
    db.add(website)
    await db.commit()
    await db.refresh(website)
    return website


async def update_website(
    db: AsyncSession, slug: str, data: WebsiteUpdate
) -> Website:
    website = await _get_website(db, slug)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(website, field, value)
    website.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(website)
    return website


async def delete_website(db: AsyncSession, slug: str) -> None:
    website = await _get_website(db, slug)
    # Clean up generated static files if they exist.
    site_dir = settings.websites_root / slug
    if site_dir.exists():
        import shutil
        shutil.rmtree(site_dir, ignore_errors=True)
    await db.delete(website)
    await db.commit()


async def get_meta_suggestions(
    db: AsyncSession, slug: str, current_user: User
) -> MetaSuggestionsResponse:
    """Return pre-computed meta field suggestions for the edit form.

    Suggestions are derived from the linked collection's metadata and from
    the users who hold Editor / EditorInChief roles on that collection.
    Intended to pre-populate empty meta_config fields on first edit.
    """
    website = await _get_website(db, slug)

    col: Collection | None = None
    if website.collection_id:
        col = await db.get(Collection, website.collection_id)

    # ── Contributor names (Editor + EiC assigned to the collection) ───────
    contributor_names: list[str] = []
    if col is not None:
        # The directly assigned editor
        if col.editor_id:
            editor = await db.get(User, col.editor_id)
            if editor:
                contributor_names.append(editor.display_name or editor.username)

        # Users with explicit permission grants who carry Editor/EiC role
        result = await db.execute(
            select(User)
            .join(CollectionPermission, CollectionPermission.user_id == User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                CollectionPermission.collection_id == col.id,
                Role.name.in_([RoleName.Editor, RoleName.EditorInChief]),
                UserRole.revoked_at.is_(None),
            )
            .distinct()
        )
        for u in result.scalars().all():
            name = u.display_name or u.username
            if name not in contributor_names:
                contributor_names.append(name)

    # ── Designer is the currently logged-in user ──────────────────────────
    designer_name = current_user.display_name or current_user.username

    # ── Publisher / copyright come from the collection's TEI metadata ─────
    publisher: str = col.publisher if col and col.publisher else ""

    # ── Identifier: use the collection's persistent identifier URL ────────
    identifier: str = col.identifier_url if col and col.identifier_url else ""

    return MetaSuggestionsResponse(
        author=contributor_names,
        dc_creator=contributor_names,
        designer=[designer_name],
        copyright=publisher,
        dc_publisher=[publisher] if publisher else [],
        dc_format="text/html",
        dc_identifier=identifier,
    )


# ── Pages ─────────────────────────────────────────────────────────────────────

async def create_website_page(
    db: AsyncSession, website_id: uuid.UUID, data: WebsitePageCreate
) -> WebsitePage:
    existing = await db.scalar(
        select(WebsitePage).where(
            WebsitePage.website_id == website_id,
            WebsitePage.slug == data.slug,
        )
    )
    if existing is not None:
        raise ConflictError(f"Page with slug '{data.slug}' already exists in this website.")

    page = WebsitePage(
        website_id=website_id,
        slug=data.slug,
        title=data.title,
        content_md=data.content_md,
        sort_order=data.sort_order,
        is_hidden=data.is_hidden,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


async def update_website_page(
    db: AsyncSession,
    website_id: uuid.UUID,
    page_slug: str,
    data: WebsitePageUpdate,
) -> WebsitePage:
    page = await db.scalar(
        select(WebsitePage).where(
            WebsitePage.website_id == website_id,
            WebsitePage.slug == page_slug,
        )
    )
    if page is None:
        raise NotFoundError(f"Page '{page_slug}' not found.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(page, field, value)
    page.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(page)
    return page


async def delete_website_page(
    db: AsyncSession, website_id: uuid.UUID, page_slug: str
) -> None:
    page = await db.scalar(
        select(WebsitePage).where(
            WebsitePage.website_id == website_id,
            WebsitePage.slug == page_slug,
        )
    )
    if page is None:
        raise NotFoundError(f"Page '{page_slug}' not found.")
    await db.delete(page)
    await db.commit()


# ── Static build (Option A) ───────────────────────────────────────────────────

async def trigger_build(db: AsyncSession, slug: str) -> None:
    """Mark the website as pending — the caller schedules _run_build as background task."""
    website = await _get_website(db, slug)
    website.build_status = BuildStatus.pending
    website.build_error = None
    website.updated_at = datetime.now(UTC)
    await db.commit()


async def run_build(slug: str) -> None:
    """Background task: generate the complete static site for *slug*.

    Creates its own AsyncSession so it can run after the HTTP response is sent.
    Rendering mode DYNAMIC and HYBRID are no-ops (their "build" is handled
    at request time); this function only executes the STATIC path.
    """
    async with AsyncSessionLocal() as db:
        try:
            website = await _get_website(db, slug)

            if website.rendering_mode != RenderingMode.STATIC:
                # Nothing to build for dynamic/hybrid modes.
                website.build_status = BuildStatus.done
                website.last_build_at = datetime.now(UTC)
                await db.commit()
                return

            website.build_status = BuildStatus.building
            website.updated_at = datetime.now(UTC)
            await db.commit()

            await _build_static_site(db, website)

            website.build_status = BuildStatus.done
            website.build_error = None
            website.last_build_at = datetime.now(UTC)
            website.updated_at = datetime.now(UTC)
            await db.commit()
            logger.info("website_build_done", slug=slug)

        except Exception as exc:
            logger.error("website_build_failed", slug=slug, error=str(exc))
            try:
                async with AsyncSessionLocal() as err_db:
                    w = await err_db.scalar(select(Website).where(Website.slug == slug))
                    if w:
                        w.build_status = BuildStatus.failed
                        w.build_error = str(exc)
                        w.updated_at = datetime.now(UTC)
                        await err_db.commit()
            except Exception:
                pass


async def _build_static_site(db: AsyncSession, website: Website) -> None:
    """Generate all HTML files for *website* into settings.websites_root / slug /.

    Output structure:
      index.html      — cover/hero page with CTA → browse.html
      browse.html     — document list
      docs/{f}.html   — per-document rendered HTML (via XSLT)
      pages/{s}.html  — free Markdown pages
      search.json     — pre-built search index for future client-side search
    """
    import defusedxml.ElementTree as ET

    slug = website.slug
    theme = website.theme_config or {}
    logo_url: str | None = theme.get("logo_url") or None

    site_dir = settings.websites_root / slug
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "docs").mkdir(exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)

    style = _style_block(theme)

    # Only visible free pages appear in the navigation.
    visible_pages = [p for p in website.pages if not p.is_hidden]

    # Resolve Aracne system-page visibility from nav_config.
    aracne_nav = _parse_aracne_nav(website.nav_config or [])
    _nav_map = {ap["id"]: ap for ap in aracne_nav}
    browse_hidden: bool = bool(_nav_map.get("browse", {}).get("is_hidden", False))
    search_hidden: bool = bool(_nav_map.get("search", {}).get("is_hidden", False))

    # Navbars for root-level pages and subdirectory pages differ only in prefix.
    def navbar(path_prefix: str = "") -> str:
        return _render_navbar(
            site_title=website.title,
            logo_url=logo_url,
            pages=visible_pages,
            path_prefix=path_prefix,
            nav_config=website.nav_config or [],
        )

    # ── Fetch collection metadata and document list ────────────────────────
    doc_infos: list[dict] = []
    col: Collection | None = None

    if website.collection_id is not None:
        col = await db.get(Collection, website.collection_id)

    if col is not None:
        col_path = existdb_client.col_path(col.slug)
        try:
            raw = await existdb_client.xquery(
                "collections/list_with_titles.xq",
                variables={"collection_path": col_path},
            )
            root_el = ET.fromstring(raw)
            for el in root_el.findall("doc"):
                filename = (el.findtext("filename") or "").strip()
                if not filename:
                    continue
                doc_infos.append(
                    {
                        "filename": filename,
                        "title": (el.findtext("title") or "").strip() or None,
                        "author": (el.findtext("author") or "").strip() or None,
                    }
                )
        except Exception as exc:
            logger.warning("website_build_list_docs_failed", slug=slug, error=str(exc))
            try:
                filenames = await existdb_client.list_collection(col.slug)
                doc_infos = [{"filename": f, "title": None, "author": None} for f in filenames]
            except Exception:
                doc_infos = []

    # Build meta tags string (same on every page of this site).
    meta_tags: str = _build_meta_tags(website.meta_config or {})

    # Build publisher / year string and identifier URL for every page footer.
    publisher_parts: list[str] = []
    identifier_url: str = ""
    if col:
        if col.publisher:
            publisher_parts.append(_html.escape(col.publisher))
        if col.pub_year:
            publisher_parts.append(str(col.pub_year))
        if col.identifier_url:
            identifier_url = col.identifier_url
    footer_note = ", ".join(publisher_parts)

    # ── index.html — cover / hero page ────────────────────────────────────
    index_html = _render_page(
        site_title=website.title,
        page_title=website.title,
        content=_build_cover_content(
            website_title=website.title,
            col=col,
            doc_count=len(doc_infos),
            theme=theme,
            pages=visible_pages,
        ),
        style=style,
        navbar=navbar(),
        footer_note=footer_note,
        identifier_url=identifier_url,
        meta_tags=meta_tags,
    )
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ── browse.html — document list (skipped when hidden) ─────────────────
    if not browse_hidden:
        browse_html = _render_page(
            site_title=website.title,
            page_title="Browse",
            content=_build_browse_content(doc_infos),
            style=style,
            navbar=navbar(),
            footer_note=footer_note,
            identifier_url=identifier_url,
            meta_tags=meta_tags,
        )
        (site_dir / "browse.html").write_text(browse_html, encoding="utf-8")

    # ── docs/{filename}.html — individual documents ────────────────────────
    if col is not None:
        for doc_info in doc_infos:
            filename = doc_info["filename"]
            try:
                xml_bytes = await existdb_client.get_document(col.slug, filename)
                doc_body = await asyncio.to_thread(_render_xml_to_html, xml_bytes)
            except Exception as exc:
                logger.warning(
                    "website_build_doc_failed", slug=slug, filename=filename, error=str(exc)
                )
                doc_body = f"<p>Could not render document: {_html.escape(str(exc))}</p>"

            label = doc_info.get("title") or filename
            doc_html = _render_page(
                site_title=website.title,
                page_title=label,
                content=f'<div class="tei-body">{doc_body}</div>',
                style=style,
                navbar=navbar("../"),
                footer_note=footer_note,
                identifier_url=identifier_url,
            )
            (site_dir / "docs" / f"{filename}.html").write_text(doc_html, encoding="utf-8")

    # ── pages/{slug}.html — free Markdown pages (hidden pages are skipped) ──
    for page in visible_pages:
        content_html = _md_to_html(page.content_md or "")
        page_html = _render_page(
            site_title=website.title,
            page_title=page.title,
            content=f"<h1>{_html.escape(page.title)}</h1>\n{content_html}",
            style=style,
            navbar=navbar("../"),
            footer_note=footer_note,
            identifier_url=identifier_url,
        )
        (site_dir / "pages" / f"{page.slug}.html").write_text(page_html, encoding="utf-8")

    # ── search.html — client-side search page (skipped when hidden) ──────
    if not search_hidden:
        search_html = _render_page(
            site_title=website.title,
            page_title="Search",
            content=_build_search_content(),
            style=style,
            navbar=navbar(),
            footer_note=footer_note,
            identifier_url=identifier_url,
            meta_tags=meta_tags,
        )
        (site_dir / "search.html").write_text(search_html, encoding="utf-8")

    # ── search.json — pre-built index for client-side search ──────────────
    search_index = [
        {
            "filename": d["filename"],
            "title": d.get("title") or d["filename"],
            "author": d.get("author") or "",
            "url": f"docs/{d['filename']}.html",
        }
        for d in doc_infos
    ]
    (site_dir / "search.json").write_text(
        json.dumps(search_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
