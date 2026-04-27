"""Business logic for search engines."""

import hashlib
import textwrap
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import ConflictError, DomainValidationError, ExternalServiceError, NotFoundError
from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal
from app.models.collection import Collection, CollectionStatus
from app.models.search_engine import (
    SearchEngine,
    SearchEngineCollection,
    SearchEngineQueryCache,
)
from app.models.website import BuildStatus
from app.models.xslt_template import XsltTemplate
from app.schemas.search_engines import (
    AdvancedSearchConfig,
    EmbedConfig,
    SearchEngineCollectionItem,
    SearchEngineCreate,
    SearchEngineResponse,
    SearchEngineUpdate,
    SearchHit,
    SearchEngineSearchResponse,
)

logger = structlog.get_logger()

_MAX_RESULTS_DEFAULT = 50
_MAX_RESULTS_LIMIT = 200


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_engine_or_404(db: AsyncSession, slug: str) -> SearchEngine:
    result = await db.execute(
        select(SearchEngine)
        .where(SearchEngine.slug == slug)
        .options(selectinload(SearchEngine.collections))
    )
    engine = result.scalar_one_or_none()
    if engine is None:
        raise NotFoundError(f"Search engine '{slug}' not found")
    return engine


def _to_response(engine: SearchEngine, collections: list[Collection]) -> SearchEngineResponse:
    """Build a SearchEngineResponse, embedding full collection info."""
    col_map: dict[uuid.UUID, Collection] = {c.id: c for c in collections}
    col_items = [
        SearchEngineCollectionItem(
            id=row.collection_id,
            slug=col_map[row.collection_id].slug,
            title=col_map[row.collection_id].title,
        )
        for row in engine.collections
        if row.collection_id in col_map
    ]
    return SearchEngineResponse(
        id=engine.id,
        slug=engine.slug,
        title=engine.title,
        xslt_template_id=engine.xslt_template_id,
        build_status=engine.build_status,
        last_build_at=engine.last_build_at,
        build_error=engine.build_error,
        cache_ttl_minutes=engine.cache_ttl_minutes,
        footer_text=engine.footer_text,
        footer_hidden=engine.footer_hidden,
        page_bg_color=engine.page_bg_color,
        header_bg_color=engine.header_bg_color,
        header_hidden=engine.header_hidden,
        custom_css=engine.custom_css,
        custom_js=engine.custom_js,
        include_jquery=engine.include_jquery,
        advanced_search_enabled=engine.advanced_search_enabled,
        advanced_search_config=AdvancedSearchConfig.model_validate(
            engine.advanced_search_config or {}
        ),
        embed_enabled=engine.embed_enabled,
        embed_config=EmbedConfig.model_validate(engine.embed_config or {}),
        collections=col_items,
        created_by=engine.created_by,
        created_at=engine.created_at,
        updated_at=engine.updated_at,
    )


async def _load_collections(
    db: AsyncSession, collection_ids: list[uuid.UUID]
) -> list[Collection]:
    """Return Collection rows for the given IDs (order preserved)."""
    if not collection_ids:
        return []
    result = await db.execute(
        select(Collection).where(Collection.id.in_(collection_ids))
    )
    return list(result.scalars().all())


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def list_search_engines(db: AsyncSession) -> list[SearchEngineResponse]:
    result = await db.execute(
        select(SearchEngine)
        .options(selectinload(SearchEngine.collections))
        .order_by(SearchEngine.title)
    )
    engines = list(result.scalars().all())

    # Bulk-load all referenced collections in one query.
    all_col_ids = {row.collection_id for e in engines for row in e.collections}
    collections = await _load_collections(db, list(all_col_ids))

    return [_to_response(e, collections) for e in engines]


async def get_search_engine(db: AsyncSession, slug: str) -> SearchEngineResponse:
    engine = await _get_engine_or_404(db, slug)
    col_ids = [row.collection_id for row in engine.collections]
    collections = await _load_collections(db, col_ids)
    return _to_response(engine, collections)


async def create_search_engine(
    db: AsyncSession,
    payload: SearchEngineCreate,
    created_by: uuid.UUID | None,
) -> SearchEngineResponse:
    # Slug uniqueness check.
    existing = await db.execute(
        select(SearchEngine).where(SearchEngine.slug == payload.slug)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"Search engine with slug '{payload.slug}' already exists")

    # Validate XSLT template if provided.
    if payload.xslt_template_id is not None:
        tpl = await db.get(XsltTemplate, payload.xslt_template_id)
        if tpl is None:
            raise NotFoundError(
                f"XSLT template '{payload.xslt_template_id}' not found"
            )

    # Validate collections: must exist and be published + public.
    collections = await _validate_collections(db, payload.collection_ids)

    engine = SearchEngine(
        slug=payload.slug,
        title=payload.title,
        xslt_template_id=payload.xslt_template_id,
        cache_ttl_minutes=payload.cache_ttl_minutes,
        footer_text=payload.footer_text or None,
        footer_hidden=payload.footer_hidden,
        page_bg_color=payload.page_bg_color or None,
        header_bg_color=payload.header_bg_color or None,
        header_hidden=payload.header_hidden,
        custom_css=payload.custom_css or None,
        custom_js=payload.custom_js or None,
        include_jquery=payload.include_jquery,
        advanced_search_enabled=payload.advanced_search_enabled,
        advanced_search_config=payload.advanced_search_config.model_dump(mode="json"),
        embed_enabled=payload.embed_enabled,
        embed_config=payload.embed_config.model_dump(mode="json"),
        created_by=created_by,
    )
    db.add(engine)
    await db.flush()  # get engine.id before inserting junction rows

    for col in collections:
        db.add(SearchEngineCollection(
            search_engine_id=engine.id,
            collection_id=col.id,
        ))

    await db.commit()
    await db.refresh(engine, ["collections"])
    return _to_response(engine, collections)


async def update_search_engine(
    db: AsyncSession,
    slug: str,
    payload: SearchEngineUpdate,
) -> SearchEngineResponse:
    engine = await _get_engine_or_404(db, slug)

    if payload.title is not None:
        engine.title = payload.title

    if payload.xslt_template_id is not None:
        tpl = await db.get(XsltTemplate, payload.xslt_template_id)
        if tpl is None:
            raise NotFoundError(
                f"XSLT template '{payload.xslt_template_id}' not found"
            )
        engine.xslt_template_id = payload.xslt_template_id
    elif "xslt_template_id" in payload.model_fields_set:
        # Explicitly set to null.
        engine.xslt_template_id = None

    if payload.cache_ttl_minutes is not None:
        engine.cache_ttl_minutes = payload.cache_ttl_minutes

    if "footer_text" in payload.model_fields_set:
        engine.footer_text = payload.footer_text or None

    if payload.footer_hidden is not None:
        engine.footer_hidden = payload.footer_hidden

    if "page_bg_color" in payload.model_fields_set:
        engine.page_bg_color = payload.page_bg_color or None

    if "header_bg_color" in payload.model_fields_set:
        engine.header_bg_color = payload.header_bg_color or None

    if payload.header_hidden is not None:
        engine.header_hidden = payload.header_hidden

    if "custom_css" in payload.model_fields_set:
        engine.custom_css = payload.custom_css or None

    if "custom_js" in payload.model_fields_set:
        engine.custom_js = payload.custom_js or None

    if payload.include_jquery is not None:
        engine.include_jquery = payload.include_jquery

    if payload.advanced_search_enabled is not None:
        engine.advanced_search_enabled = payload.advanced_search_enabled

    if payload.advanced_search_config is not None:
        engine.advanced_search_config = payload.advanced_search_config.model_dump(
            mode="json"
        )

    if payload.embed_enabled is not None:
        engine.embed_enabled = payload.embed_enabled

    if payload.embed_config is not None:
        engine.embed_config = payload.embed_config.model_dump(mode="json")

    collections: list[Collection] = []
    if payload.collection_ids is not None:
        collections = await _validate_collections(db, payload.collection_ids)
        # Replace junction rows.
        await db.execute(
            SearchEngineCollection.__table__.delete().where(
                SearchEngineCollection.search_engine_id == engine.id
            )
        )
        for col in collections:
            db.add(SearchEngineCollection(
                search_engine_id=engine.id,
                collection_id=col.id,
            ))
    else:
        col_ids = [row.collection_id for row in engine.collections]
        collections = await _load_collections(db, col_ids)

    await db.commit()
    await db.refresh(engine, ["collections"])
    return _to_response(engine, collections)


async def delete_search_engine(db: AsyncSession, slug: str) -> None:
    engine = await _get_engine_or_404(db, slug)
    await db.delete(engine)
    await db.commit()


async def clear_cache(db: AsyncSession, slug: str) -> int:
    """Delete all cached query results for a search engine.

    Returns the number of deleted entries.
    """
    engine = await _get_engine_or_404(db, slug)
    result = await db.execute(
        delete(SearchEngineQueryCache).where(
            SearchEngineQueryCache.search_engine_id == engine.id
        )
    )
    await db.commit()
    deleted: int = result.rowcount
    logger.info("search_engine_cache_cleared", slug=slug, deleted=deleted)
    return deleted


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _build_cache_key(q: str, collection_slugs: list[str]) -> str:
    """Return a deterministic SHA-256 hex cache key."""
    normalized = q.strip().lower()
    cols = "|".join(sorted(collection_slugs))
    return hashlib.sha256(f"{normalized}\x00{cols}".encode()).hexdigest()


async def _get_from_cache(
    db: AsyncSession,
    engine_id: uuid.UUID,
    query_hash: str,
) -> SearchEngineQueryCache | None:
    """Return a valid (non-expired) cache entry, or None on miss."""
    result = await db.execute(
        select(SearchEngineQueryCache).where(
            SearchEngineQueryCache.search_engine_id == engine_id,
            SearchEngineQueryCache.query_hash == query_hash,
            SearchEngineQueryCache.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def _write_to_cache(
    db: AsyncSession,
    engine_id: uuid.UUID,
    query_hash: str,
    query_text: str,
    collections_key: str,
    hits: list[SearchHit],
    ttl_minutes: int,
) -> None:
    """Upsert a cache entry (INSERT … ON CONFLICT DO UPDATE)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    hits_data = [h.model_dump(mode="json") for h in hits]

    stmt = pg_insert(SearchEngineQueryCache).values(
        id=uuid.uuid4(),
        search_engine_id=engine_id,
        query_hash=query_hash,
        query_text=query_text,
        collections_key=collections_key,
        hits=hits_data,
        total=len(hits_data),
        created_at=datetime.now(UTC),
        expires_at=expires,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["search_engine_id", "query_hash"],
        set_={
            "hits": stmt.excluded.hits,
            "total": stmt.excluded.total,
            "created_at": stmt.excluded.created_at,
            "expires_at": stmt.excluded.expires_at,
        },
    )
    await db.execute(stmt)
    await db.commit()


# ── Public search ─────────────────────────────────────────────────────────────

async def run_search(
    db: AsyncSession,
    slug: str,
    q: str,
    collection_slugs: list[str] | None,
    max_results: int,
) -> tuple[SearchEngineSearchResponse, int]:
    """Execute a cross-collection full-text search for the given search engine.

    Returns a (response, cache_ttl_minutes) tuple so the caller can set
    appropriate Cache-Control headers.  cache_ttl_minutes is 0 when caching
    is disabled or the result is trivially empty.

    Results are served from the PostgreSQL cache when available and not expired.
    Cache is bypassed when cache_ttl_minutes == 0.
    """
    import defusedxml.ElementTree as ET  # noqa: PLC0415

    if max_results < 1:
        max_results = _MAX_RESULTS_DEFAULT
    if max_results > _MAX_RESULTS_LIMIT:
        max_results = _MAX_RESULTS_LIMIT

    engine = await _get_engine_or_404(db, slug)
    col_ids = [row.collection_id for row in engine.collections]

    if not col_ids:
        return SearchEngineSearchResponse(query=q, total=0, hits=[]), 0

    # Load collections and build slug→col map.
    collections = await _load_collections(db, col_ids)

    # Restrict to requested slugs if provided.
    target_cols: list[Collection] = []
    if collection_slugs:
        allowed_slugs = {c.slug for c in collections}
        for s in collection_slugs:
            if s not in allowed_slugs:
                raise NotFoundError(
                    f"Collection '{s}' is not linked to search engine '{slug}'"
                )
        target_cols = [c for c in collections if c.slug in set(collection_slugs)]
    else:
        target_cols = collections

    if not target_cols:
        return SearchEngineSearchResponse(query=q, total=0, hits=[]), 0

    target_slugs = [c.slug for c in target_cols]
    collections_key = "|".join(sorted(target_slugs))
    cache_key = _build_cache_key(q, target_slugs)

    # ── Cache check ───────────────────────────────────────────────────────────
    if engine.cache_ttl_minutes > 0:
        cached_entry = await _get_from_cache(db, engine.id, cache_key)
        if cached_entry is not None:
            cached_hits = [SearchHit(**h) for h in cached_entry.hits]
            logger.debug("search_engine_cache_hit", slug=slug, query=q)
            return SearchEngineSearchResponse(
                query=q,
                total=cached_entry.total,
                hits=cached_hits,
                cached=True,
            ), engine.cache_ttl_minutes

    # ── Cache miss — run XQuery ───────────────────────────────────────────────
    paths_csv = ",".join(existdb_client.col_path(c.slug) for c in target_cols)
    path_to_slug: dict[str, str] = {
        existdb_client.col_path(c.slug): c.slug for c in target_cols
    }

    try:
        raw = await existdb_client.xquery(
            "search/search_engine_search.xq",
            variables={
                "collection_paths_csv": paths_csv,
                "query": q,
                "max_results": str(max_results),
            },
        )
    except ExternalServiceError as exc:
        logger.error("search_engine_xquery_failed", slug=slug, error=str(exc))
        return SearchEngineSearchResponse(query=q, total=0, hits=[]), 0

    try:
        root_el = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.error("search_engine_xml_parse_failed", slug=slug, error=str(exc))
        return SearchEngineSearchResponse(query=q, total=0, hits=[]), 0

    hits: list[SearchHit] = []
    for hit_el in root_el.findall("hit"):
        col_path = hit_el.get("collection_path", "")
        col_slug = path_to_slug.get(col_path, col_path.rsplit("/", 1)[-1])
        filename = hit_el.get("filename", "")
        raw_title = (hit_el.get("title") or "").strip()
        kwic_el = hit_el.find("kwic")
        kwic_text = kwic_el.text or "" if kwic_el is not None else ""
        hits.append(SearchHit(
            collection_slug=col_slug,
            filename=filename,
            title=raw_title if raw_title else None,
            doc_url=f"/browse/{col_slug}/{filename}?highlight={urllib.parse.quote(q)}",
            score=float(hit_el.get("score", "0")),
            mode=hit_el.get("mode", "contains"),
            kwic=kwic_text,
        ))

    # ── Write to cache ────────────────────────────────────────────────────────
    if engine.cache_ttl_minutes > 0:
        await _write_to_cache(
            db,
            engine_id=engine.id,
            query_hash=cache_key,
            query_text=q,
            collections_key=collections_key,
            hits=hits,
            ttl_minutes=engine.cache_ttl_minutes,
        )

    return SearchEngineSearchResponse(query=q, total=len(hits), hits=hits, cached=False), engine.cache_ttl_minutes


# ── Collection validation helper ──────────────────────────────────────────────

async def _validate_collections(
    db: AsyncSession, collection_ids: list[uuid.UUID]
) -> list[Collection]:
    """Return Collection rows after verifying they are published and public."""
    if not collection_ids:
        return []
    rows = await _load_collections(db, collection_ids)
    found_ids = {c.id for c in rows}
    for cid in collection_ids:
        if cid not in found_ids:
            raise NotFoundError(f"Collection '{cid}' not found")
        col = next(c for c in rows if c.id == cid)
        if col.status != CollectionStatus.published or not col.is_public:
            raise ConflictError(
                f"Collection '{col.slug}' is not published and public"
            )
    return rows


# ── Available tags ────────────────────────────────────────────────────────────

async def get_available_tags(db: AsyncSession, slug: str) -> dict[str, list[str]]:
    """Return the merged element→attributes map across all linked collections.

    Runs ``collections/distinct_tags.xq`` once per linked collection and
    merges the results by taking the union of attribute names per element.
    Collections that fail to scan are skipped with a warning.
    """
    import json as _json  # noqa: PLC0415

    engine = await _get_engine_or_404(db, slug)
    col_ids = [row.collection_id for row in engine.collections]
    if not col_ids:
        return {}

    collections = await _load_collections(db, col_ids)
    merged: dict[str, set[str]] = {}

    for col in collections:
        path = existdb_client.col_path(col.slug)
        try:
            raw = await existdb_client.xquery(
                "collections/distinct_tags.xq", {"path": path}
            )
            data: dict[str, list[str]] = _json.loads(raw.decode("utf-8"))
            for elem, attrs in data.items():
                if elem not in merged:
                    merged[elem] = set()
                merged[elem].update(attrs)
        except Exception as exc:
            logger.warning(
                "search_engine_tags_scan_failed",
                slug=slug,
                collection=col.slug,
                error=str(exc),
            )

    return {k: sorted(v) for k, v in sorted(merged.items())}


# ── Public collection listing ─────────────────────────────────────────────────

async def list_public_collections(db: AsyncSession) -> list[dict[str, Any]]:
    """Return all published + public collections for the D+ assignment UI."""
    result = await db.execute(
        select(Collection)
        .where(
            Collection.status == CollectionStatus.published,
            Collection.is_public.is_(True),
        )
        .order_by(Collection.title)
    )
    cols = list(result.scalars().all())
    return [{"id": str(c.id), "slug": c.slug, "title": c.title} for c in cols]


# ── Build ─────────────────────────────────────────────────────────────────────

def _footer_html(footer_text: str | None, footer_hidden: bool = False) -> str:
    """Return the footer element for built search-engine pages, or empty string when hidden."""
    if footer_hidden:
        return ""
    import html as _html  # noqa: PLC0415

    credit = '<a href="https://github.com/orazionelson/aracne2" target="_blank" rel="noopener">Aracne2</a>'
    note = f'<span>{_html.escape(footer_text)}</span> &middot; ' if footer_text else ""
    return f"          <footer>{note}Built with {credit}</footer>"


def _theme_css_block(
    page_bg_color: str | None,
    header_bg_color: str | None,
    header_hidden: bool,
) -> str:
    """Return a <style> block that applies the theme overrides, or empty string.

    Foreground colours are auto-derived from each background's luminance
    (WCAG sRGB formula, via :func:`app.services.websites._readable_text_on`)
    so admins can pick any hex value without breaking text contrast — the
    same adaptive behaviour already used by websites and the public
    homepage navbar.
    """
    from app.services.websites import _readable_text_on  # noqa: PLC0415

    rules: list[str] = []
    if page_bg_color:
        page_text = _readable_text_on(page_bg_color)
        rules.append(f"    body {{ background: {page_bg_color} !important; }}")
        if page_text:
            rules.append(f"    body {{ color: {page_text} !important; }}")
    if header_bg_color:
        header_text = _readable_text_on(header_bg_color)
        rules.append(f"    header {{ background: {header_bg_color} !important; }}")
        if header_text:
            # The header inherits its own color and contains the title +
            # (advanced page) the link back to simple search; both must
            # remain readable on the chosen bg.
            rules.append(f"    header, header h1 {{ color: {header_text} !important; }}")
            rules.append(f"    header a {{ color: {header_text} !important; }}")
    if header_hidden:
        rules.append("    header { display: none !important; }")
        rules.append("    main { margin-top: 1.5rem; }")
    if not rules:
        return ""
    return "\n  <style>\n" + "\n".join(rules) + "\n  </style>"


def _custom_css_block(custom_css: str | None) -> str:
    """Return a <style> block with sanitised custom CSS, or empty string."""
    if not custom_css or not custom_css.strip():
        return ""
    safe = custom_css.replace("</style>", "")
    return f"\n  <style>\n    /* custom */\n{safe}\n  </style>"


def _custom_js_block(custom_js: str | None, include_jquery: bool) -> str:
    """Return script tag(s) for optional jQuery + custom JS, or empty string."""
    parts: list[str] = []
    if include_jquery:
        parts.append(
            '  <script src="https://code.jquery.com/jquery-3.7.1.min.js"'
            ' integrity="sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo="'
            ' crossorigin="anonymous"></script>'
        )
    if custom_js and custom_js.strip():
        safe = custom_js.replace("</script>", "")
        parts.append(f"  <script>\n{safe}\n  </script>")
    return ("\n" + "\n".join(parts)) if parts else ""


def _render_search_page(
    slug: str,
    title: str,
    advanced_search_enabled: bool = False,
    page_bg_color: str | None = None,
    header_bg_color: str | None = None,
    header_hidden: bool = False,
    custom_css: str | None = None,
    custom_js: str | None = None,
    include_jquery: bool = False,
    footer_text: str | None = None,
    footer_hidden: bool = False,
) -> str:
    """Generate the standalone HTML search page for a search engine.

    The page is self-contained: a search form whose JS calls the public
    API endpoint and renders results inline.  No external JS/CSS dependencies.
    """
    api_endpoint = f"/api/v1/search-engines/{slug}/search"
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    adv_link = (
        f'<p style="margin:0 0 1.5rem;font-size:0.85rem;">'
        f'<a href="/api/v1/search-pages/{slug}/advanced/" '
        f'style="color:#1e3a5f;">&#9658; Ricerca avanzata</a></p>'
        if advanced_search_enabled
        else ""
    )
    theme_css = _theme_css_block(page_bg_color, header_bg_color, header_hidden)
    extra_css = _custom_css_block(custom_css)
    extra_js = _custom_js_block(custom_js, include_jquery)

    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <base target="_top" />
          <title>{escaped_title}</title>
          <style>
            *, *::before, *::after {{ box-sizing: border-box; }}
            body {{
              font-family: system-ui, -apple-system, sans-serif;
              margin: 0;
              background: #f9fafb;
              color: #111827;
            }}
            header {{
              background: #1e3a5f;
              color: #fff;
              padding: 1.25rem 2rem;
            }}
            header h1 {{ margin: 0; font-size: 1.4rem; font-weight: 600; }}
            main {{ max-width: 800px; margin: 2rem auto; padding: 0 1.5rem; }}
            #search-form {{
              display: flex;
              gap: 0.5rem;
              margin-bottom: 1.5rem;
            }}
            #q {{
              flex: 1;
              padding: 0.6rem 1rem;
              border: 1px solid #d1d5db;
              border-radius: 0.375rem;
              font-size: 1rem;
            }}
            #q:focus {{ outline: none; border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }}
            button[type=submit] {{
              padding: 0.6rem 1.25rem;
              background: #1e3a5f;
              color: #fff;
              border: none;
              border-radius: 0.375rem;
              font-size: 1rem;
              cursor: pointer;
            }}
            button[type=submit]:hover {{ background: #2d4f7f; }}
            #status {{ font-size: 0.875rem; color: #6b7280; margin-bottom: 1rem; }}
            article {{
              background: #fff;
              border: 1px solid #e5e7eb;
              border-radius: 0.5rem;
              padding: 1rem 1.25rem;
              margin-bottom: 0.75rem;
            }}
            article h3 {{
              margin: 0 0 0.4rem;
              font-size: 1rem;
              color: #1e3a5f;
            }}
            article h3 a {{ color: #1e3a5f; text-decoration: none; }}
            article h3 a:hover {{ text-decoration: underline; }}
            article .meta {{
              font-size: 0.75rem;
              color: #9ca3af;
              margin-bottom: 0.5rem;
            }}
            article p {{ margin: 0; font-size: 0.9rem; color: #374151; line-height: 1.5; }}
            footer {{
              text-align: center; font-size: 0.75rem; color: #9ca3af;
              padding: 1.5rem; margin-top: 2rem; border-top: 1px solid #e5e7eb;
            }}
            footer a {{ color: #6b7280; }}
            footer a:hover {{ text-decoration: underline; }}
          </style>{theme_css}{extra_css}
        </head>
        <body>
          <header><h1>{escaped_title}</h1></header>
          <main>
            <form id="search-form" role="search">
              <input
                type="search"
                id="q"
                name="q"
                placeholder="Search..."
                autocomplete="off"
                autofocus
              />
              <button type="submit">Search</button>
            </form>
            {adv_link}
            <div id="status"></div>
            <div id="results" role="region" aria-live="polite"></div>
          </main>
{_footer_html(footer_text, footer_hidden)}
          <script>
            (function () {{
              var API = {api_endpoint!r};
              var form = document.getElementById('search-form');
              var qInput = document.getElementById('q');
              var statusEl = document.getElementById('status');
              var resultsEl = document.getElementById('results');

              // Session-level cache: query string → API data object.
              var _cache = new Map();

              function escapeHtml(str) {{
                return String(str)
                  .replace(/&/g, '&amp;')
                  .replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;')
                  .replace(/"/g, '&quot;');
              }}

              function renderResults(data) {{
                if (data.total === 0) {{
                  statusEl.textContent = 'No results for "' + escapeHtml(data.query) + '".';
                  resultsEl.innerHTML = '';
                  return;
                }}
                statusEl.textContent = data.total + ' snippet' + (data.total !== 1 ? 's' : '') +
                  ' for "' + escapeHtml(data.query) + '"';
                resultsEl.innerHTML = data.hits.map(function (h) {{
                  var label = h.title || h.filename;
                  var meta  = escapeHtml(h.collection_slug) + ' \u00b7 ' + escapeHtml(h.filename);
                  return '<article>' +
                    '<h3><a href="' + escapeHtml(h.doc_url) + '">' + escapeHtml(label) + '</a></h3>' +
                    '<div class="meta">' + meta + '</div>' +
                    '<p>' + escapeHtml(h.kwic) + '</p>' +
                    '</article>';
                }}).join('');
              }}

              form.addEventListener('submit', function (e) {{
                e.preventDefault();
                var q = qInput.value.trim();
                if (!q) return;

                // Serve from in-page session cache when available.
                if (_cache.has(q)) {{
                  renderResults(_cache.get(q));
                  return;
                }}

                statusEl.textContent = 'Searching\u2026';
                resultsEl.innerHTML = '';
                fetch(API + '?q=' + encodeURIComponent(q))
                  .then(function (r) {{ return r.json(); }})
                  .then(function (json) {{
                    _cache.set(q, json.data);
                    renderResults(json.data);
                  }})
                  .catch(function () {{ statusEl.textContent = 'Search error. Please try again.'; }});
              }});

              // Auto-search if ?q= is in the URL.
              var urlQ = new URLSearchParams(location.search).get('q');
              if (urlQ) {{
                qInput.value = urlQ;
                form.dispatchEvent(new Event('submit'));
              }}
            }})();
          </script>{extra_js}
        </body>
        </html>
    """)


def _render_advanced_search_page(
    slug: str,
    title: str,
    config: AdvancedSearchConfig,
    collections: list[Collection],
    page_bg_color: str | None = None,
    header_bg_color: str | None = None,
    header_hidden: bool = False,
    custom_css: str | None = None,
    custom_js: str | None = None,
    include_jquery: bool = False,
    footer_text: str | None = None,
    footer_hidden: bool = False,
) -> str:
    """Generate the standalone HTML advanced search page for a search engine.

    The page is built once (at Build time) and calls the public advanced-search
    API dynamically.  The named_tags and attribute_filters configured by the
    admin are baked in as JS arrays.

    Named tags and attribute filters are rendered as visible radio-button groups
    so the user immediately sees all available options without opening a dropdown.
    The attribute-value input is revealed only when a specific attribute radio
    is selected.
    """
    api_endpoint = f"/api/v1/search-engines/{slug}/advanced-search"
    main_page = f"/api/v1/search-pages/{slug}/"
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    theme_css = _theme_css_block(page_bg_color, header_bg_color, header_hidden)
    extra_css = _custom_css_block(custom_css)
    extra_js = _custom_js_block(custom_js, include_jquery)

    # Bake admin config into JS.
    named_tags_js = "[" + ",".join(
        f'{{"label":{t.label!r},"element":{t.element!r}}}'
        for t in config.named_tags
    ) + "]"
    attr_filters_js = "[" + ",".join(
        f'{{"label":{f.label!r},"attribute":{f.attribute!r}}}'
        for f in config.attribute_filters
    ) + "]"
    collection_list_js = "[" + ",".join(
        f'{{"slug":{c.slug!r},"title":{c.title!r}}}'
        for c in collections
    ) + "]"

    show_collections = len(collections) > 1

    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="it">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <base target="_top" />
          <title>{escaped_title} — Ricerca avanzata</title>
          <style>
            *, *::before, *::after {{ box-sizing: border-box; }}
            body {{
              font-family: system-ui, -apple-system, sans-serif;
              margin: 0; background: #f9fafb; color: #111827;
            }}
            header {{
              background: #1e3a5f; color: #fff; padding: 1.25rem 2rem;
              display: flex; align-items: baseline; gap: 1rem;
            }}
            header h1 {{ margin: 0; font-size: 1.4rem; font-weight: 600; }}
            header a {{ color: #93c5fd; font-size: 0.85rem; text-decoration: none; }}
            header a:hover {{ text-decoration: underline; }}
            main {{ max-width: 820px; margin: 2rem auto; padding: 0 1.5rem; }}
            .field {{ margin-bottom: 1.25rem; }}
            .field-label {{
              display: block; font-size: 0.8rem; font-weight: 600;
              color: #374151; margin-bottom: 0.4rem;
            }}
            input[type=text], input[type=search] {{
              width: 100%; padding: 0.55rem 0.9rem;
              border: 1px solid #d1d5db; border-radius: 0.375rem; font-size: 0.95rem;
            }}
            input[type=text]:focus, input[type=search]:focus {{
              outline: none; border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe;
            }}
            /* Radio-button group replacing <select> */
            .radio-group {{
              display: flex; flex-wrap: wrap; gap: 0.4rem 0;
              padding: 0.5rem 0.75rem;
              border: 1px solid #d1d5db; border-radius: 0.375rem; background: #fff;
            }}
            .radio-opt {{
              display: flex; align-items: center; gap: 0.4rem;
              padding: 0.3rem 0.6rem; border-radius: 0.25rem;
              cursor: pointer; font-size: 0.9rem; font-weight: 400;
              color: #374151; transition: background 0.1s;
            }}
            .radio-opt:hover {{ background: #f3f4f6; }}
            .radio-opt input[type=radio] {{ cursor: pointer; accent-color: #1e3a5f; }}
            .radio-opt.any-opt {{ color: #9ca3af; font-style: italic; }}
            .radio-opt input[type=radio]:checked + span {{ color: #1e3a5f; font-weight: 600; }}
            .collections-grid {{
              display: flex; flex-wrap: wrap; gap: 0.5rem 1.25rem;
              padding: 0.6rem 0.9rem; border: 1px solid #d1d5db;
              border-radius: 0.375rem; background: #fff;
            }}
            .collections-grid label {{
              font-weight: 400; display: flex; align-items: center; gap: 0.4rem; cursor: pointer;
            }}
            button[type=submit] {{
              padding: 0.6rem 1.5rem; background: #1e3a5f; color: #fff;
              border: none; border-radius: 0.375rem; font-size: 1rem; cursor: pointer;
            }}
            button[type=submit]:hover {{ background: #2d4f7f; }}
            #status {{ font-size: 0.875rem; color: #6b7280; margin: 1rem 0; }}
            article {{
              background: #fff; border: 1px solid #e5e7eb;
              border-radius: 0.5rem; padding: 1rem 1.25rem; margin-bottom: 0.75rem;
            }}
            article h3 {{ margin: 0 0 0.35rem; font-size: 1rem; color: #1e3a5f; }}
            article h3 a {{ color: #1e3a5f; text-decoration: none; }}
            article h3 a:hover {{ text-decoration: underline; }}
            article .meta {{ font-size: 0.72rem; color: #9ca3af; margin-bottom: 0.4rem; }}
            article p {{ margin: 0; font-size: 0.9rem; color: #374151; line-height: 1.5; }}
            .tag-badge {{
              display: inline-block; font-size: 0.7rem; font-family: monospace;
              background: #e0f2fe; color: #0369a1; border-radius: 0.25rem;
              padding: 0.1rem 0.4rem; margin-right: 0.4rem;
            }}
            footer {{
              text-align: center; font-size: 0.75rem; color: #9ca3af;
              padding: 1.5rem; margin-top: 2rem; border-top: 1px solid #e5e7eb;
            }}
            footer a {{ color: #6b7280; }}
            footer a:hover {{ text-decoration: underline; }}
          </style>{theme_css}{extra_css}
        </head>
        <body>
          <header>
            <h1>{escaped_title}</h1>
            <a href="{main_page}">&#8592; Ricerca semplice</a>
          </header>
          <main>
            <form id="adv-form">

              <!-- Collection filter (only if >1 collection) -->
              <div class="field" id="col-field" {"" if show_collections else 'style="display:none"'}>
                <span class="field-label">Collezioni</span>
                <div class="collections-grid" id="col-grid"></div>
              </div>

              <!-- Named tag radio group (hidden until JS populates it) -->
              <div class="field" id="tag-field" style="display:none">
                <span class="field-label">Cerca all'interno del tag</span>
                <div class="radio-group" id="tag-radios">
                  <label class="radio-opt any-opt">
                    <input type="radio" name="sel-tag" value="" checked />
                    <span>qualsiasi elemento</span>
                  </label>
                </div>
              </div>

              <!-- Text search input (always visible) -->
              <div class="field">
                <label class="field-label" for="tag-q">Testo da cercare</label>
                <input type="search" id="tag-q" placeholder="es. Uccello" autocomplete="off" />
              </div>

              <!-- Attribute filter radio group (hidden until JS populates it) -->
              <div class="field" id="attr-field" style="display:none">
                <span class="field-label">Filtra per attributo</span>
                <div class="radio-group" id="attr-radios">
                  <label class="radio-opt any-opt">
                    <input type="radio" name="sel-attr" value="" checked />
                    <span>nessun filtro</span>
                  </label>
                </div>
              </div>

              <!-- Attribute value input (revealed when a specific attr is selected) -->
              <div class="field" id="attr-val-field" style="display:none">
                <label class="field-label" for="attr-val">Valore dell'attributo</label>
                <input type="text" id="attr-val" placeholder="es. Conte" autocomplete="off" />
              </div>

              <div id="form-error" style="color:#dc2626;font-size:0.85rem;margin-bottom:0.75rem;"></div>
              <button type="submit">Cerca</button>
            </form>

            <div id="status"></div>
            <div id="results" role="region" aria-live="polite"></div>
          </main>
{_footer_html(footer_text, footer_hidden)}
          <script>
            (function () {{
              var API          = {api_endpoint!r};
              var NAMED_TAGS   = {named_tags_js};
              var ATTR_FILTERS = {attr_filters_js};
              var COLLECTIONS  = {collection_list_js};
              var SHOW_COLS    = {'true' if show_collections else 'false'};

              var form        = document.getElementById('adv-form');
              var statusEl    = document.getElementById('status');
              var resultsEl   = document.getElementById('results');
              var errEl       = document.getElementById('form-error');
              var tagField    = document.getElementById('tag-field');
              var tagRadios   = document.getElementById('tag-radios');
              var tagQ        = document.getElementById('tag-q');
              var attrField   = document.getElementById('attr-field');
              var attrRadios  = document.getElementById('attr-radios');
              var attrValField = document.getElementById('attr-val-field');
              var attrVal     = document.getElementById('attr-val');
              var colGrid     = document.getElementById('col-grid');

              // ── Populate tag radio group ───────────────────────────────────
              NAMED_TAGS.forEach(function (t) {{
                var lbl = document.createElement('label');
                lbl.className = 'radio-opt';
                var rb = document.createElement('input');
                rb.type = 'radio'; rb.name = 'sel-tag'; rb.value = t.element;
                var sp = document.createElement('span');
                sp.textContent = t.label + ' \u003c' + t.element + '\u003e';
                lbl.appendChild(rb); lbl.appendChild(sp);
                tagRadios.appendChild(lbl);
              }});
              if (NAMED_TAGS.length > 0) tagField.style.display = '';

              // ── Populate attribute radio group ────────────────────────────
              ATTR_FILTERS.forEach(function (f) {{
                var lbl = document.createElement('label');
                lbl.className = 'radio-opt';
                var rb = document.createElement('input');
                rb.type = 'radio'; rb.name = 'sel-attr'; rb.value = f.attribute;
                var sp = document.createElement('span');
                sp.textContent = f.label + ' (@' + f.attribute + ')';
                lbl.appendChild(rb); lbl.appendChild(sp);
                attrRadios.appendChild(lbl);
              }});
              if (ATTR_FILTERS.length > 0) attrField.style.display = '';

              // Show / hide attribute-value input on radio change.
              attrRadios.addEventListener('change', function (e) {{
                if (e.target.name === 'sel-attr') {{
                  if (e.target.value) {{
                    attrValField.style.display = '';
                  }} else {{
                    attrValField.style.display = 'none';
                    attrVal.value = '';
                  }}
                }}
              }});

              // ── Populate collection checkboxes ────────────────────────────
              if (SHOW_COLS) {{
                COLLECTIONS.forEach(function (c) {{
                  var lbl = document.createElement('label');
                  var cb  = document.createElement('input');
                  cb.type = 'checkbox'; cb.value = c.slug; cb.checked = true;
                  lbl.appendChild(cb);
                  lbl.appendChild(document.createTextNode(' ' + c.title));
                  colGrid.appendChild(lbl);
                }});
              }}

              // ── HTML escaping ─────────────────────────────────────────────
              function escapeHtml(str) {{
                return String(str)
                  .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
              }}

              // ── Result rendering ──────────────────────────────────────────
              function renderResults(data) {{
                if (!data.hits || data.hits.length === 0) {{
                  statusEl.textContent = 'Nessun risultato.';
                  resultsEl.innerHTML = '';
                  return;
                }}
                statusEl.textContent = data.hits.length +
                  ' risultato' + (data.hits.length !== 1 ? 'i' : '') + ' trovato' +
                  (data.hits.length !== 1 ? 'i' : '') + '.';
                resultsEl.innerHTML = data.hits.map(function (h) {{
                  var label = h.title || h.filename;
                  var badge = h.element_name
                    ? '<span class="tag-badge">&lt;' + escapeHtml(h.element_name) + '&gt;</span>'
                    : '';
                  var meta = escapeHtml(h.collection_slug) + ' \u00b7 ' + escapeHtml(h.filename);
                  return '<article>' +
                    '<h3>' + badge + '<a href="' + escapeHtml(h.doc_url) + '">' +
                    escapeHtml(label) + '</a></h3>' +
                    '<div class="meta">' + meta + '</div>' +
                    '<p>' + escapeHtml(h.kwic) + '</p>' +
                    '</article>';
                }}).join('');
              }}

              // ── Form submit ───────────────────────────────────────────────
              form.addEventListener('submit', function (e) {{
                e.preventDefault();
                errEl.textContent = '';

                var checkedTag  = tagRadios.querySelector('input[name="sel-tag"]:checked');
                var element     = checkedTag  ? checkedTag.value  : '';
                var q           = tagQ.value.trim();
                var checkedAttr = attrRadios.querySelector('input[name="sel-attr"]:checked');
                var attrName    = checkedAttr ? checkedAttr.value : '';
                var attrV       = attrVal.value.trim();

                if (!element && !q && !attrName) {{
                  errEl.textContent = 'Inserisci almeno un criterio di ricerca.';
                  return;
                }}

                var params = new URLSearchParams();
                if (q)        params.set('q',         q);
                if (element)  params.set('element',   element);
                if (attrName) params.set('attr_name',  attrName);
                if (attrV)    params.set('attr_value', attrV);

                if (SHOW_COLS) {{
                  var checked = [];
                  colGrid.querySelectorAll('input[type=checkbox]:checked').forEach(
                    function (cb) {{ checked.push(cb.value); }}
                  );
                  if (checked.length > 0 && checked.length < COLLECTIONS.length) {{
                    params.set('collections', checked.join(','));
                  }}
                }}

                statusEl.textContent = 'Ricerca in corso\u2026';
                resultsEl.innerHTML = '';

                fetch(API + '?' + params.toString())
                  .then(function (r) {{ return r.json(); }})
                  .then(function (json) {{ renderResults(json.data); }})
                  .catch(function () {{
                    statusEl.textContent = 'Errore di ricerca. Riprova.';
                  }});
              }});
            }})();
          </script>{extra_js}
        </body>
        </html>
    """)


async def run_advanced_search(
    db: AsyncSession,
    slug: str,
    q: str | None,
    element_name: str | None,
    attr_name: str | None,
    attr_value: str | None,
    collection_slugs: list[str] | None,
    max_results: int,
) -> SearchEngineSearchResponse:
    """Execute an advanced structural/text search for the given search engine.

    At least one of q, element_name, attr_name must be provided.
    Results are NOT cached (advanced queries are expected to be specific/infrequent).
    """
    import defusedxml.ElementTree as ET  # noqa: PLC0415

    if max_results < 1:
        max_results = _MAX_RESULTS_DEFAULT
    if max_results > _MAX_RESULTS_LIMIT:
        max_results = _MAX_RESULTS_LIMIT

    engine = await _get_engine_or_404(db, slug)

    col_ids = [row.collection_id for row in engine.collections]
    if not col_ids:
        return SearchEngineSearchResponse(query=q or "", total=0, hits=[])

    collections = await _load_collections(db, col_ids)
    if collection_slugs:
        allowed = {c.slug for c in collections}
        for s in collection_slugs:
            if s not in allowed:
                raise NotFoundError(
                    f"Collection '{s}' is not linked to search engine '{slug}'"
                )
        target_cols = [c for c in collections if c.slug in set(collection_slugs)]
    else:
        target_cols = collections

    if not target_cols:
        return SearchEngineSearchResponse(query=q or "", total=0, hits=[])

    paths_csv = ",".join(existdb_client.col_path(c.slug) for c in target_cols)
    path_to_slug: dict[str, str] = {
        existdb_client.col_path(c.slug): c.slug for c in target_cols
    }

    try:
        raw = await existdb_client.xquery(
            "search/search_engine_advanced.xq",
            variables={
                "collection_paths_csv": paths_csv,
                "query": q or "",
                "element_name": element_name or "",
                "attr_name": attr_name or "",
                "attr_value": attr_value or "",
                "max_results": str(max_results),
            },
        )
    except ExternalServiceError as exc:
        logger.error("search_engine_advanced_xquery_failed", slug=slug, error=str(exc))
        return SearchEngineSearchResponse(query=q or "", total=0, hits=[])

    try:
        root_el = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.error(
            "search_engine_advanced_xml_parse_failed", slug=slug, error=str(exc)
        )
        return SearchEngineSearchResponse(query=q or "", total=0, hits=[])

    hits: list[SearchHit] = []
    for hit_el in root_el.findall("hit"):
        col_path = hit_el.get("collection_path", "")
        col_slug = path_to_slug.get(col_path, col_path.rsplit("/", 1)[-1])
        filename = hit_el.get("filename", "")
        raw_title = (hit_el.get("title") or "").strip()
        element = hit_el.get("element", "") or None
        kwic_el = hit_el.find("kwic")
        kwic_text = kwic_el.text or "" if kwic_el is not None else ""
        highlight = urllib.parse.quote(q) if q else urllib.parse.quote(
            hit_el.get("element", "") or ""
        )
        hits.append(SearchHit(
            collection_slug=col_slug,
            filename=filename,
            title=raw_title if raw_title else None,
            doc_url=f"/browse/{col_slug}/{filename}?highlight={highlight}",
            score=float(hit_el.get("score", "0")),
            mode=hit_el.get("mode", "advanced-structural"),
            kwic=kwic_text,
            element_name=element,
        ))

    return SearchEngineSearchResponse(query=q or "", total=len(hits), hits=hits)


async def _do_build(slug: str) -> None:
    """Background task: generate the search page HTML and write it to disk."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(SearchEngine)
                .where(SearchEngine.slug == slug)
                .options(selectinload(SearchEngine.collections))
            )
            engine = result.scalar_one_or_none()
            if engine is None:
                return

            engine.build_status = BuildStatus.building
            await db.commit()

            out_dir = settings.search_engines_root / slug
            if not out_dir.resolve().is_relative_to(settings.search_engines_root.resolve()):
                raise DomainValidationError(code="INVALID_SLUG", message="Slug resolves outside the allowed directory")
            out_dir.mkdir(parents=True, exist_ok=True)

            # Main search page.
            html = _render_search_page(
                engine.slug,
                engine.title,
                engine.advanced_search_enabled,
                page_bg_color=engine.page_bg_color,
                header_bg_color=engine.header_bg_color,
                header_hidden=engine.header_hidden,
                custom_css=engine.custom_css,
                custom_js=engine.custom_js,
                include_jquery=engine.include_jquery,
                footer_text=engine.footer_text,
                footer_hidden=engine.footer_hidden,
            )
            (out_dir / "index.html").write_text(html, encoding="utf-8")

            # Advanced search page (built only when the feature is enabled).
            if engine.advanced_search_enabled:
                col_ids = [row.collection_id for row in engine.collections]
                cols = await _load_collections(db, col_ids)
                config = AdvancedSearchConfig.model_validate(
                    engine.advanced_search_config or {}
                )
                adv_html = _render_advanced_search_page(
                    engine.slug,
                    engine.title,
                    config,
                    cols,
                    page_bg_color=engine.page_bg_color,
                    header_bg_color=engine.header_bg_color,
                    header_hidden=engine.header_hidden,
                    custom_css=engine.custom_css,
                    custom_js=engine.custom_js,
                    include_jquery=engine.include_jquery,
                    footer_text=engine.footer_text,
                    footer_hidden=engine.footer_hidden,
                )
                adv_dir = out_dir / "advanced"
                adv_dir.mkdir(parents=True, exist_ok=True)
                (adv_dir / "index.html").write_text(adv_html, encoding="utf-8")

            engine.build_status = BuildStatus.done
            engine.last_build_at = datetime.now(UTC)
            engine.build_error = None
            await db.commit()
            logger.info("search_engine_build_done", slug=slug)

        except Exception as exc:
            logger.error("search_engine_build_failed", slug=slug, error=str(exc))
            try:
                engine.build_status = BuildStatus.failed
                engine.build_error = str(exc)
                await db.commit()
            except Exception:
                pass


async def trigger_build(db: AsyncSession, slug: str) -> SearchEngineResponse:
    """Mark the search engine as pending and return immediately.

    The caller is responsible for scheduling _do_build() as a background task.
    """
    engine = await _get_engine_or_404(db, slug)
    if engine.build_status == BuildStatus.building:
        raise ConflictError("Build already in progress")

    engine.build_status = BuildStatus.pending
    engine.build_error = None
    await db.commit()
    await db.refresh(engine, ["collections"])

    col_ids = [row.collection_id for row in engine.collections]
    collections = await _load_collections(db, col_ids)
    return _to_response(engine, collections)
