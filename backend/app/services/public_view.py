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
    """Fetch filenames, titles and authors from eXist-db via XQuery.

    Falls back to filename-only list (without title/author) if the XQuery
    fails or returns malformed XML.
    """
    col_path = existdb_client.col_path(slug)
    try:
        raw = await existdb_client.xquery(
            "collections/list_with_titles.xq",
            variables={"collection_path": col_path},
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
        # Graceful fallback: plain filename list
        try:
            filenames = await existdb_client.list_collection(slug)
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
        xml_bytes = await existdb_client.get_document(slug, filename)
    except Exception as exc:
        raise NotFoundError(f"Document '{filename}' not found.") from exc

    try:
        transform = _get_transform()
        # lxml.etree.fromstring is safe here: the XML comes from our own
        # eXist-db instance, not from untrusted user input.
        xml_doc = etree.fromstring(xml_bytes)  # noqa: S320
        result = transform(xml_doc)
        html = str(result)
        html = html.replace("</body>", f"{_HIGHLIGHT_SCRIPT}</body>", 1)
        return html
    except Exception as exc:
        logger.error("render_document_failed", slug=slug, filename=filename, error=str(exc))
        raise DomainValidationError(
            "RENDER_ERROR", f"Could not render document: {exc}"
        ) from exc
