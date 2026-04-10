"""Business logic for search engines."""

import textwrap
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ExternalServiceError
from app.db.existdb import existdb_client
from app.db.postgres import AsyncSessionLocal
from app.models.collection import Collection, CollectionStatus
from app.models.search_engine import SearchEngine, SearchEngineCollection
from app.models.website import BuildStatus
from app.models.xslt_template import XsltTemplate
from app.schemas.search_engines import (
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


# ── Public search ─────────────────────────────────────────────────────────────

async def run_search(
    db: AsyncSession,
    slug: str,
    q: str,
    collection_slugs: list[str] | None,
    max_results: int,
) -> SearchEngineSearchResponse:
    """Execute a cross-collection full-text search for the given search engine."""
    import defusedxml.ElementTree as ET  # noqa: PLC0415

    if max_results < 1:
        max_results = _MAX_RESULTS_DEFAULT
    if max_results > _MAX_RESULTS_LIMIT:
        max_results = _MAX_RESULTS_LIMIT

    engine = await _get_engine_or_404(db, slug)
    col_ids = [row.collection_id for row in engine.collections]

    if not col_ids:
        return SearchEngineSearchResponse(query=q, total=0, hits=[])

    # Load collections and build slug→col map.
    collections = await _load_collections(db, col_ids)
    col_by_id: dict[uuid.UUID, Collection] = {c.id: c for c in collections}

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
        return SearchEngineSearchResponse(query=q, total=0, hits=[])

    # Build comma-separated path list for the XQuery.
    paths_csv = ",".join(existdb_client.col_path(c.slug) for c in target_cols)
    # Build slug lookup keyed by eXist-db path.
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
        return SearchEngineSearchResponse(query=q, total=0, hits=[])

    try:
        root_el = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.error("search_engine_xml_parse_failed", slug=slug, error=str(exc))
        return SearchEngineSearchResponse(query=q, total=0, hits=[])

    hits: list[SearchHit] = []
    for hit_el in root_el.findall("hit"):
        col_path = hit_el.get("collection_path", "")
        col_slug = path_to_slug.get(col_path, col_path.rsplit("/", 1)[-1])
        kwic_el = hit_el.find("kwic")
        kwic_text = kwic_el.text or "" if kwic_el is not None else ""
        hits.append(SearchHit(
            collection_slug=col_slug,
            filename=hit_el.get("filename", ""),
            score=float(hit_el.get("score", "0")),
            mode=hit_el.get("mode", "contains"),
            kwic=kwic_text,
        ))

    return SearchEngineSearchResponse(query=q, total=len(hits), hits=hits)


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

def _render_search_page(slug: str, title: str) -> str:
    """Generate the standalone HTML search page for a search engine.

    The page is self-contained: a search form whose JS calls the public
    API endpoint and renders results inline.  No external JS/CSS dependencies.
    """
    api_endpoint = f"/api/v1/search-engines/{slug}/search"
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")

    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
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
            article .meta {{
              font-size: 0.75rem;
              color: #9ca3af;
              margin-bottom: 0.5rem;
            }}
            article p {{ margin: 0; font-size: 0.9rem; color: #374151; line-height: 1.5; }}
          </style>
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
            <div id="status"></div>
            <div id="results" role="region" aria-live="polite"></div>
          </main>
          <script>
            (function () {{
              var API = {api_endpoint!r};
              var form = document.getElementById('search-form');
              var qInput = document.getElementById('q');
              var statusEl = document.getElementById('status');
              var resultsEl = document.getElementById('results');

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
                statusEl.textContent = data.total + ' result' + (data.total !== 1 ? 's' : '') +
                  ' for "' + escapeHtml(data.query) + '"';
                resultsEl.innerHTML = data.hits.map(function (h) {{
                  return '<article>' +
                    '<h3>' + escapeHtml(h.filename) + '</h3>' +
                    '<div class="meta">' + escapeHtml(h.collection_slug) + '</div>' +
                    '<p>' + escapeHtml(h.kwic) + '</p>' +
                    '</article>';
                }}).join('');
              }}

              form.addEventListener('submit', function (e) {{
                e.preventDefault();
                var q = qInput.value.trim();
                if (!q) return;
                statusEl.textContent = 'Searching\u2026';
                resultsEl.innerHTML = '';
                fetch(API + '?q=' + encodeURIComponent(q))
                  .then(function (r) {{ return r.json(); }})
                  .then(function (json) {{ renderResults(json.data); }})
                  .catch(function () {{ statusEl.textContent = 'Search error. Please try again.'; }});
              }});

              // Auto-search if ?q= is in the URL.
              var urlQ = new URLSearchParams(location.search).get('q');
              if (urlQ) {{
                qInput.value = urlQ;
                form.dispatchEvent(new Event('submit'));
              }}
            }})();
          </script>
        </body>
        </html>
    """)


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

            html = _render_search_page(engine.slug, engine.title)

            out_dir = settings.search_engines_root / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text(html, encoding="utf-8")

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
