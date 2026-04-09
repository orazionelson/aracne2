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
from app.models.website import BuildStatus, RenderingMode, Website, WebsitePage
from app.schemas.websites import WebsiteCreate, WebsitePageCreate, WebsitePageUpdate, WebsiteUpdate

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

# Static CSS injected into every generated page; theme colours are set via
# :root custom properties in the per-page <style> block.
_STATIC_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Georgia, "Times New Roman", serif;
  color: var(--text);
  background: var(--bg);
  line-height: 1.7;
  font-size: 1rem;
}
header {
  background: var(--primary);
  padding: 0 1.5rem;
}
nav {
  display: flex;
  gap: 1.5rem;
  align-items: center;
  max-width: 960px;
  margin: 0 auto;
  height: 3rem;
  flex-wrap: wrap;
}
.brand {
  color: #fff;
  text-decoration: none;
  font-weight: bold;
  font-size: 1.05rem;
  margin-right: auto;
}
nav a {
  color: rgba(255,255,255,0.85);
  text-decoration: none;
  font-size: 0.875rem;
}
nav a:hover { color: #fff; }
main {
  max-width: 960px;
  margin: 2.5rem auto;
  padding: 0 1.5rem;
}
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; line-height: 1.2; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.75rem; }
p { margin-bottom: 1rem; }
a { color: var(--primary); }
ul { margin: 0.5rem 0 1rem 1.5rem; }
li { margin-bottom: 0.3rem; }
.doc-list { list-style: none; margin-left: 0; }
.doc-list li {
  border-bottom: 1px solid #e5e7eb;
  padding: 0.6rem 0;
}
.doc-list a { font-weight: 500; }
.doc-meta { font-size: 0.85rem; color: #6b7280; margin-top: 0.1rem; }
.tei-body { border-top: 1px solid #e5e7eb; padding-top: 1.5rem; margin-top: 1.5rem; }
footer {
  margin-top: 4rem;
  border-top: 1px solid #e5e7eb;
  padding: 1rem 1.5rem;
  text-align: center;
  font-size: 0.78rem;
  color: #9ca3af;
}
"""


def _style_block(theme: dict) -> str:
    primary = _html.escape(theme.get("primary_color", "#1e293b"))
    text = _html.escape(theme.get("text_color", "#1e293b"))
    bg = _html.escape(theme.get("bg_color", "#ffffff"))
    root_vars = f":root{{--primary:{primary};--text:{text};--bg:{bg};}}"
    return f"<style>\n{root_vars}\n{_STATIC_CSS}\n</style>"


def _nav_links(pages: list[WebsitePage], path_prefix: str = "") -> str:
    links = ""
    for page in pages:
        href = f"{path_prefix}pages/{_html.escape(page.slug)}.html"
        links += f'<a href="{href}">{_html.escape(page.title)}</a>\n'
    return links


def _render_page(
    *,
    site_title: str,
    page_title: str,
    content: str,
    style: str,
    nav: str,
    path_prefix: str = "",
) -> str:
    esc_site = _html.escape(site_title)
    esc_page = _html.escape(page_title)
    docs_href = f"{path_prefix}index.html"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc_page} — {esc_site}</title>
  {style}
</head>
<body>
  <header>
    <nav>
      <a class="brand" href="{docs_href}">{esc_site}</a>
      {nav}
    </nav>
  </header>
  <main>
    {content}
  </main>
  <footer>Built with <a href="https://github.com/orazio-nelson/aracne2">Aracne2</a></footer>
</body>
</html>"""


def _md_to_html(content_md: str) -> str:
    """Minimal Markdown→HTML converter: headings, paragraphs, line breaks."""
    lines = content_md.splitlines()
    blocks: list[str] = []
    para_lines: list[str] = []

    def flush_para() -> None:
        if para_lines:
            blocks.append(f"<p>{'<br>'.join(_html.escape(l) for l in para_lines)}</p>")
            para_lines.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_para()
        elif stripped.startswith("### "):
            flush_para()
            blocks.append(f"<h3>{_html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            flush_para()
            blocks.append(f"<h2>{_html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            flush_para()
            blocks.append(f"<h2>{_html.escape(stripped[2:])}</h2>")
        else:
            para_lines.append(stripped)

    flush_para()
    return "\n".join(blocks)


def _render_xml_to_html(xml_bytes: bytes) -> str:
    """Apply the generic TEI XSLT and return the <body> inner HTML."""
    transform = _get_transform()
    xml_doc = etree.fromstring(xml_bytes)  # noqa: S320 — from our own eXist-db
    result = transform(xml_doc)
    result_str = str(result)
    # Extract the content inside <body>...</body> if present; else use all.
    body_match = re.search(r"<body[^>]*>(.*?)</body>", result_str, re.DOTALL | re.IGNORECASE)
    return body_match.group(1) if body_match else result_str


def _build_index_content(col: Collection, docs: list[dict]) -> str:
    title = _html.escape(col.title or "")
    description = f"<p>{_html.escape(col.description)}</p>" if col.description else ""
    author = f"<p><em>{_html.escape(col.author)}</em></p>" if col.author else ""
    meta = ""
    if col.publisher or col.pub_year:
        parts = []
        if col.publisher:
            parts.append(_html.escape(col.publisher))
        if col.pub_year:
            parts.append(str(col.pub_year))
        meta = f"<p class='doc-meta'>{', '.join(parts)}</p>"

    items = ""
    for doc in docs:
        filename = _html.escape(doc["filename"])
        label = _html.escape(doc.get("title") or doc["filename"])
        author_line = (
            f'<div class="doc-meta">{_html.escape(doc["author"])}</div>'
            if doc.get("author")
            else ""
        )
        items += (
            f'<li><a href="docs/{filename}.html">{label}</a>{author_line}</li>\n'
        )

    return f"""
<h1>{title}</h1>
{author}
{description}
{meta}
<h2>Documents</h2>
<ul class="doc-list">
{items}
</ul>
"""


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
    """Generate all HTML files for *website* into settings.websites_root / slug /."""
    import defusedxml.ElementTree as ET

    slug = website.slug
    site_dir = settings.websites_root / slug
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "docs").mkdir(exist_ok=True)
    (site_dir / "pages").mkdir(exist_ok=True)

    style = _style_block(website.theme_config or {})
    pages_nav = _nav_links(website.pages, path_prefix="../")
    root_pages_nav = _nav_links(website.pages)

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

    # ── Index page ─────────────────────────────────────────────────────────
    if col is not None:
        index_content = _build_index_content(col, doc_infos)
    else:
        index_content = f"<h1>{_html.escape(website.title)}</h1>"
        if website.description:
            index_content += f"<p>{_html.escape(website.description)}</p>"

    index_html = _render_page(
        site_title=website.title,
        page_title=website.title,
        content=index_content,
        style=style,
        nav=root_pages_nav,
    )
    (site_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ── Document pages ─────────────────────────────────────────────────────
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
                nav=pages_nav,
                path_prefix="../",
            )
            out_path = site_dir / "docs" / f"{filename}.html"
            out_path.write_text(doc_html, encoding="utf-8")

    # ── Free pages ─────────────────────────────────────────────────────────
    for page in website.pages:
        content_html = _md_to_html(page.content_md or "")
        page_html = _render_page(
            site_title=website.title,
            page_title=page.title,
            content=f"<h1>{_html.escape(page.title)}</h1>\n{content_html}",
            style=style,
            nav=pages_nav,
            path_prefix="../",
        )
        (site_dir / "pages" / f"{page.slug}.html").write_text(page_html, encoding="utf-8")

    # ── Search index (JSON for client-side use in future phases) ──────────
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
