"""public_view — service for unauthenticated public browsing.

Exposes published, is_public=True collections and renders their documents
to HTML via the built-in XSLT 1.0 stylesheet (app/xslt/tei_generic.xsl).

The XSLT file is loaded once per process and cached to avoid repeated
filesystem reads on every request.
"""

from pathlib import Path

import defusedxml.ElementTree as ET
import structlog
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.db.existdb import existdb_client
from app.models.collection import Collection, CollectionStatus
from app.schemas.public_view import PublicCollectionDetail, PublicDocumentInfo
from app.services.settings import get_decrypted_setting
from app.services.websites import (
    _build_entity_hover_js,
    _build_note_rendering_css,
    _build_note_rendering_js,
)
from app.services.xmldb import _natural_sort_key

logger = structlog.get_logger()

# Path to the built-in generic TEI→HTML stylesheet.
_XSLT_PATH = Path(__file__).parent.parent / "xslt" / "tei_generic.xsl"

# Module-level XSLT transform cache.
_xslt_transform: etree.XSLT | None = None

# Inline script injected into every rendered document.
# Reads ?highlight=TERM from location.search, wraps matching text nodes in
# <mark> elements, and smooth-scrolls to the first match.
# Exits silently when ?highlight is absent — safe to inject unconditionally.
# Entity-hover CSS — copy of the rules embedded in websites.py's
# _STATIC_CSS, scoped here so the public-document iframe can opt in
# without inheriting the whole website stylesheet. Inert until the
# JS in _build_entity_hover_js inserts a .tei-entity-hover-tip node.
_ENTITY_HOVER_CSS = (
    ".tei-entity-hover-tip{position:absolute;z-index:1000;max-width:280px;"
    "background:#1e293b;color:#f8fafc;padding:.5rem .7rem;border-radius:6px;"
    "box-shadow:0 4px 18px rgba(0,0,0,.35);font-size:.82rem;line-height:1.4;"
    "pointer-events:none;}"
    ".tei-entity-hover-tip img.tei-entity-hover-img{display:block;"
    "max-width:100%;max-height:140px;object-fit:contain;border-radius:3px;"
    "margin-bottom:.4rem;background:rgba(255,255,255,.04);}"
    ".tei-entity-hover-tip .tei-entity-hover-label{font-weight:600;"
    "margin-bottom:.15rem;color:#f8fafc;}"
    ".tei-entity-hover-tip .tei-entity-hover-desc{color:#cbd5e1;"
    "font-size:.78rem;font-style:italic;}"
    ".tei-entity-hover-tip .tei-entity-hover-src{color:#94a3b8;"
    "font-size:.7rem;margin-top:.35rem;letter-spacing:.02em;}"
    ".tei-entity-hover-tip .tei-entity-hover-loading,"
    ".tei-entity-hover-tip .tei-entity-hover-error{color:#cbd5e1;"
    "font-style:italic;}"
    "a.tei-persname.tei-has-preview,"
    "a.tei-placename.tei-has-preview,"
    "a.tei-orgname.tei-has-preview{"
    "border-bottom-style:dashed;border-bottom-width:1.5px;}"
)


_HIGHLIGHT_SCRIPT = (
    '<script>(function(){'
    'var m=location.search.match(/[?&]highlight=([^&]+)/);'
    'if(!m)return;'
    'var term=decodeURIComponent(m[1].replace(/\\+/g," ")).trim();'
    'if(!term)return;'
    'var root=document.querySelector(".tei-body")||document.querySelector("main");'
    'if(!root)return;'
    'function esc(s){return s.replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&");}'
    'var re=new RegExp("("+esc(term)+")","gi");'
    'var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null,false);'
    'var nodes=[];'
    'var n;'
    'while((n=tw.nextNode())){'
    'if(/^(script|style|mark)$/i.test(n.parentNode.nodeName))continue;'
    'if(re.test(n.textContent))nodes.push(n);'
    're.lastIndex=0;'
    '}'
    'nodes.forEach(function(tn){'
    'var parts=tn.textContent.split(re);'
    'if(parts.length<2)return;'
    'var frag=document.createDocumentFragment();'
    'parts.forEach(function(p,i){'
    'if(i%2===1){var mk=document.createElement("mark");mk.textContent=p;frag.appendChild(mk);}'
    'else if(p)frag.appendChild(document.createTextNode(p));'
    '});'
    'tn.parentNode.replaceChild(frag,tn);'
    '});'
    'var first=root.querySelector("mark");'
    'if(first)first.scrollIntoView({behavior:"smooth",block:"center"});'
    '})();</script>'
)


def _get_transform() -> etree.XSLT:
    """Load and cache the XSLT transform.  Thread-safe for asyncio (single loop)."""
    global _xslt_transform
    if _xslt_transform is None:
        xslt_doc = etree.parse(str(_XSLT_PATH))
        _xslt_transform = etree.XSLT(xslt_doc)
    return _xslt_transform


async def get_public_collection(db: AsyncSession, slug: str) -> Collection:
    """Return a published + is_public collection, or raise NotFoundError."""
    col = await db.scalar(
        select(Collection).where(
            Collection.slug == slug,
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
    )
    if col is None:
        raise NotFoundError(f"Collection '{slug}' not found or not publicly available.")
    return col


async def _list_documents_with_titles(slug: str) -> list[PublicDocumentInfo]:
    """Fetch filenames, titles and authors from the published snapshot.

    Public surfaces (this view, the website router, the sitemap) read from
    ``existdb.published_path(slug)`` so editors can keep modifying the
    working tree without leaking partial states to anonymous visitors.
    Falls back to filename-only list (without title/author) if the XQuery
    fails or returns malformed XML.
    """
    published_path = existdb_client.published_path(slug)
    try:
        raw = await existdb_client.xquery(
            "collections/list_with_titles.xq",
            variables={"collection_path": published_path},
        )
        root = ET.fromstring(raw)
        docs: list[PublicDocumentInfo] = []
        for el in root.findall("doc"):
            filename = (el.findtext("filename") or "").strip()
            if not filename:
                continue
            title = (el.findtext("title") or "").strip() or None
            author = (el.findtext("author") or "").strip() or None
            docs.append(PublicDocumentInfo(filename=filename, title=title, author=author))
        docs.sort(key=lambda d: _natural_sort_key(d.filename))
        return docs
    except Exception as exc:
        logger.warning("public_view_list_titles_failed", slug=slug, error=str(exc))
        # Graceful fallback: plain filename list from the same snapshot.
        try:
            filenames = await existdb_client.list_published(slug)
            filenames.sort(key=_natural_sort_key)
            return [PublicDocumentInfo(filename=f, title=None, author=None) for f in filenames]
        except Exception:
            return []


async def get_public_collection_detail(
    db: AsyncSession,
    slug: str,
) -> PublicCollectionDetail:
    """Return collection metadata and sorted document list for public view."""
    col = await get_public_collection(db, slug)
    documents = await _list_documents_with_titles(slug)
    return PublicCollectionDetail(
        slug=col.slug,
        title=col.title,
        description=col.description,
        author=col.author,
        publisher=col.publisher,
        pub_year=col.pub_year,
        documents=documents,
    )


async def _read_render_overrides(db: AsyncSession) -> tuple[str, bool]:
    """Read the public-document rendering knobs from system_settings.

    Returns ``(note_mode, entity_hover_enabled)`` with safe defaults so a
    missing row never breaks the renderer.
    """
    note_mode = (await get_decrypted_setting(db, "public_pages_note_mode")) or "end-of-text"
    if note_mode not in {"end-of-text", "tooltip", "frame"}:
        note_mode = "end-of-text"
    eh_raw = (await get_decrypted_setting(db, "public_pages_entity_hover_enabled")) or "false"
    return note_mode, eh_raw == "true"


def _build_public_overrides(note_mode: str, entity_hover: bool) -> tuple[str, str]:
    """Compose the extra ``<style>`` and ``<script>`` blocks to inject.

    Reuses the website helpers so behaviour stays identical to a website
    that has note_rendering and entity_hover enabled in its xslt_config.
    """
    css_parts: list[str] = []
    js_parts: list[str] = []

    nr_cfg = {"enabled": note_mode != "end-of-text", "mode": note_mode}
    nr_css = _build_note_rendering_css(nr_cfg)
    nr_js = _build_note_rendering_js(nr_cfg)
    if nr_css:
        css_parts.append(nr_css)
    if nr_js:
        js_parts.append(nr_js)

    if entity_hover:
        css_parts.append(_ENTITY_HOVER_CSS)
        js_parts.append(_build_entity_hover_js({"enabled": True}))

    style_block = f"<style>{''.join(css_parts)}</style>" if css_parts else ""
    script_block = f"<script>{''.join(js_parts)}</script>" if js_parts else ""
    return style_block, script_block


async def render_document_html(
    db: AsyncSession,
    slug: str,
    filename: str,
) -> str:
    """Fetch a document from eXist-db and render it to HTML via XSLT.

    Raises NotFoundError if the collection or document is not publicly
    accessible.  Raises DomainValidationError if the XSLT transform fails.
    """
    await get_public_collection(db, slug)

    try:
        xml_bytes = await existdb_client.get_published_document(slug, filename)
    except Exception as exc:
        raise NotFoundError(f"Document '{filename}' not found.") from exc

    note_mode, entity_hover = await _read_render_overrides(db)
    extra_style, extra_script = _build_public_overrides(note_mode, entity_hover)

    try:
        transform = _get_transform()
        # The TEI bytes ultimately come from an Editor, who writes them
        # to eXist-db with their own role — eXist is not a trust
        # boundary against XXE. Parse with a hardened parser that
        # disables external entity resolution and network access; this
        # mirrors the schemas.py pattern and closes CVE-2026-41066 on
        # lxml 5.x default behaviour.
        _safe_parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        xml_doc = etree.fromstring(xml_bytes, parser=_safe_parser)
        result = transform(xml_doc)
        html = str(result)
        if extra_style:
            html = html.replace("</head>", f"{extra_style}</head>", 1)
        tail = f"{extra_script}{_HIGHLIGHT_SCRIPT}"
        html = html.replace("</body>", f"{tail}</body>", 1)
        return html
    except Exception as exc:
        logger.error("render_document_failed", slug=slug, filename=filename, error=str(exc))
        raise DomainValidationError(
            "RENDER_ERROR", f"Could not render document: {exc}"
        ) from exc
