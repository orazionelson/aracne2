"""Business logic for the search engine embed widget."""

from __future__ import annotations

import math
import textwrap
from datetime import UTC, datetime

import structlog
from fastapi import Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.search_engine import SearchEngine
from app.models.search_engine_embed_log import SearchEngineEmbedLog
from app.schemas.common import PaginatedResponse, PaginationMeta
from app.schemas.search_engines import (
    EmbedConfig,
    EmbedLogEntry,
    SearchEngineSearchResponse,
)
from app.services.search_engines import run_advanced_search, run_search

logger = structlog.get_logger(__name__)

_LOG_PAGE_SIZE = 50


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_embed_engine(db: AsyncSession, slug: str) -> SearchEngine:
    """Load an embed-enabled SearchEngine or raise 404/403."""
    result = await db.execute(
        select(SearchEngine).where(SearchEngine.slug == slug)
    )
    engine = result.scalar_one_or_none()
    if engine is None:
        raise NotFoundError(f"Search engine '{slug}' not found")
    if not engine.embed_enabled:
        raise NotFoundError(f"Embed widget is not enabled for '{slug}'")
    return engine


def _check_origin(engine: SearchEngine, origin: str | None) -> bool:
    """Return True when the request origin is allowed.

    An empty allowed_origins list means all origins are permitted (open embed).
    """
    config = EmbedConfig.model_validate(engine.embed_config or {})
    if not config.allowed_origins:
        return True
    if origin is None:
        return False
    # Normalise: strip trailing slash.
    norm = origin.rstrip("/")
    return any(norm == allowed.rstrip("/") for allowed in config.allowed_origins)


def _client_ip(request: Request) -> str | None:
    """Extract the best-guess client IP from request headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


async def _log(
    db: AsyncSession,
    engine: SearchEngine,
    request: Request,
    query: str,
    mode: str,
    allowed: bool,
) -> None:
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    ip = _client_ip(request)
    db.add(
        SearchEngineEmbedLog(
            search_engine_id=engine.id,
            origin=origin[:512] if origin else None,
            referer=referer[:512] if referer else None,
            ip_address=ip,
            query=query[:512],
            mode=mode,
            allowed=allowed,
            requested_at=datetime.now(UTC),
        )
    )
    await db.commit()


# ── Public search endpoints ───────────────────────────────────────────────────

async def search_embed(
    db: AsyncSession,
    slug: str,
    q: str,
    collections: list[str] | None,
    max_results: int,
    request: Request,
) -> SearchEngineSearchResponse:
    """Full-text embed search: origin check → log → run_search."""
    engine = await _get_embed_engine(db, slug)
    origin = request.headers.get("origin")
    allowed = _check_origin(engine, origin)
    await _log(db, engine, request, q, "simple", allowed)
    if not allowed:
        logger.warning("embed_origin_blocked", slug=slug, origin=origin)
        raise AuthorizationError(
            f"Origin '{origin}' is not authorised to use this embed widget"
        )
    return await run_search(db, slug, q, collections, max_results)


async def advanced_search_embed(
    db: AsyncSession,
    slug: str,
    q: str | None,
    element_name: str | None,
    attr_name: str | None,
    attr_value: str | None,
    collections: list[str] | None,
    max_results: int,
    request: Request,
) -> SearchEngineSearchResponse:
    """Advanced embed search: origin check → log → run_advanced_search."""
    engine = await _get_embed_engine(db, slug)
    origin = request.headers.get("origin")
    allowed = _check_origin(engine, origin)
    await _log(db, engine, request, q or "", "advanced", allowed)
    if not allowed:
        logger.warning("embed_origin_blocked_advanced", slug=slug, origin=origin)
        raise AuthorizationError(
            f"Origin '{origin}' is not authorised to use this embed widget"
        )
    return await run_advanced_search(
        db, slug, q, element_name, attr_name, attr_value, collections, max_results
    )


# ── Widget JS generation ──────────────────────────────────────────────────────

def _widget_js(slug: str, mode: str) -> str:
    """Generate the self-contained JS widget code.

    The code derives the API base URL from the script's own src attribute so
    that no server URL needs to be hard-coded.  It can be served as widget.js
    OR embedded inline in a <script> block.
    """
    show_simple = mode in ("simple", "both")
    show_advanced = mode in ("advanced", "both")
    show_tabs = mode == "both"

    # Produce JS booleans.
    js_simple = "true" if show_simple else "false"
    js_advanced = "true" if show_advanced else "false"
    js_tabs = "true" if show_tabs else "false"

    return textwrap.dedent(f"""\
        (function () {{
          'use strict';

          /* ── Config ────────────────────────────────────────────────────────── */
          var SLUG       = {slug!r};
          var SHOW_SIMPLE   = {js_simple};
          var SHOW_ADVANCED = {js_advanced};
          var SHOW_TABS     = {js_tabs};

          /* Derive API base from this script's src, or fall back to page origin. */
          var _scriptEl = document.currentScript ||
            (function () {{
              var scripts = document.getElementsByTagName('script');
              return scripts[scripts.length - 1];
            }})();
          var API_BASE = (function () {{
            try {{
              var src = _scriptEl.src || '';
              var m = src.match(/^(https?:\\/\\/[^\\/]+)/);
              return m ? m[1] : window.location.origin;
            }} catch (e) {{ return window.location.origin; }}
          }})();

          /* Target div: data-target attribute or default id */
          var targetId = (_scriptEl.getAttribute && _scriptEl.getAttribute('data-target'))
            || ('aracne2-' + SLUG);
          var root = document.getElementById(targetId);
          if (!root) {{ return; }}

          /* ── Styles ─────────────────────────────────────────────────────────── */
          var style = document.createElement('style');
          style.textContent = [
            '.arc2w {{font-family:system-ui,-apple-system,sans-serif;font-size:0.95rem;color:#111827;box-sizing:border-box;}}',
            '.arc2w *{{box-sizing:border-box;}}',
            '.arc2w .arc2-tabs{{display:flex;gap:0;border-bottom:2px solid #e5e7eb;margin-bottom:1rem;}}',
            '.arc2w .arc2-tab{{padding:0.5rem 1.25rem;background:none;border:none;border-bottom:2px solid transparent;cursor:pointer;font-size:0.85rem;color:#6b7280;margin-bottom:-2px;}}',
            '.arc2w .arc2-tab.active{{color:#1e3a5f;border-bottom-color:#1e3a5f;font-weight:600;}}',
            '.arc2w .arc2-panel{{display:none;}}.arc2w .arc2-panel.active{{display:block;}}',
            '.arc2w .arc2-row{{display:flex;gap:0.5rem;margin-bottom:0.75rem;}}',
            '.arc2w input[type=search],.arc2w input[type=text]{{flex:1;padding:0.5rem 0.75rem;border:1px solid #d1d5db;border-radius:0.375rem;font-size:0.9rem;}}',
            '.arc2w input:focus{{outline:none;border-color:#3b82f6;box-shadow:0 0 0 2px #bfdbfe;}}',
            '.arc2w .arc2-btn{{padding:0.5rem 1rem;background:#1e3a5f;color:#fff;border:none;border-radius:0.375rem;cursor:pointer;font-size:0.9rem;}}',
            '.arc2w .arc2-btn:hover{{background:#2d4f7f;}}',
            '.arc2w .arc2-field{{margin-bottom:0.75rem;}}',
            '.arc2w .arc2-label{{display:block;font-size:0.78rem;font-weight:600;color:#374151;margin-bottom:0.3rem;}}',
            '.arc2w .arc2-status{{font-size:0.8rem;color:#6b7280;margin:0.5rem 0;}}',
            '.arc2w .arc2-card{{background:#fff;border:1px solid #e5e7eb;border-radius:0.5rem;padding:0.75rem 1rem;margin-bottom:0.5rem;}}',
            '.arc2w .arc2-card h4{{margin:0 0 0.25rem;font-size:0.9rem;color:#1e3a5f;}}',
            '.arc2w .arc2-card h4 a{{color:#1e3a5f;text-decoration:none;}}',
            '.arc2w .arc2-card h4 a:hover{{text-decoration:underline;}}',
            '.arc2w .arc2-card .arc2-meta{{font-size:0.72rem;color:#9ca3af;margin-bottom:0.3rem;}}',
            '.arc2w .arc2-card p{{margin:0;font-size:0.85rem;color:#374151;line-height:1.4;}}',
          ].join('');
          document.head.appendChild(style);

          /* ── HTML skeleton ──────────────────────────────────────────────────── */
          root.className = 'arc2w';
          var html = '';

          if (SHOW_TABS) {{
            html += '<div class="arc2-tabs">' +
              '<button class="arc2-tab active" data-panel="arc2-simple">Ricerca</button>' +
              '<button class="arc2-tab" data-panel="arc2-advanced">Avanzata</button>' +
              '</div>';
          }}

          if (SHOW_SIMPLE) {{
            html += '<div class="arc2-panel' + (SHOW_TABS || !SHOW_ADVANCED ? ' active' : '') + '" id="arc2-simple-' + SLUG + '">' +
              '<div class="arc2-row">' +
              '<input type="search" class="arc2-q-simple" placeholder="Cerca..." autocomplete="off" />' +
              '<button class="arc2-btn arc2-submit-simple">Cerca</button>' +
              '</div>' +
              '<div class="arc2-status arc2-status-simple"></div>' +
              '<div class="arc2-results arc2-results-simple"></div>' +
              '</div>';
          }}

          if (SHOW_ADVANCED) {{
            html += '<div class="arc2-panel' + (!SHOW_TABS && SHOW_ADVANCED ? ' active' : '') + '" id="arc2-advanced-' + SLUG + '">' +
              '<div class="arc2-field">' +
              '<label class="arc2-label">Cerca nel testo</label>' +
              '<input type="search" class="arc2-q-adv" placeholder="es. Uccello" autocomplete="off" />' +
              '</div>' +
              '<div class="arc2-row"><button class="arc2-btn arc2-submit-adv">Cerca</button></div>' +
              '<div class="arc2-status arc2-status-adv"></div>' +
              '<div class="arc2-results arc2-results-adv"></div>' +
              '</div>';
          }}

          root.innerHTML = html;

          /* ── Tab switching ──────────────────────────────────────────────────── */
          if (SHOW_TABS) {{
            root.querySelectorAll('.arc2-tab').forEach(function (btn) {{
              btn.addEventListener('click', function () {{
                root.querySelectorAll('.arc2-tab').forEach(function (b) {{ b.classList.remove('active'); }});
                root.querySelectorAll('.arc2-panel').forEach(function (p) {{ p.classList.remove('active'); }});
                btn.classList.add('active');
                var panelId = btn.getAttribute('data-panel') + '-' + SLUG;
                var panel = document.getElementById(panelId);
                if (panel) panel.classList.add('active');
              }});
            }});
          }}

          /* ── Utilities ──────────────────────────────────────────────────────── */
          function esc(s) {{
            return String(s)
              .replace(/&/g,'&amp;').replace(/</g,'&lt;')
              .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
          }}

          function renderHits(hits, statusEl, resultsEl, query, total) {{
            if (!hits || hits.length === 0) {{
              statusEl.textContent = 'Nessun risultato per "' + query + '".';
              resultsEl.innerHTML = '';
              return;
            }}
            statusEl.textContent = total + ' risultato' + (total !== 1 ? 'i' : '') + ' per "' + query + '"';
            resultsEl.innerHTML = hits.map(function (h) {{
              var label = h.title || h.filename;
              return '<div class="arc2-card">' +
                '<h4><a href="' + esc(h.doc_url) + '" target="_blank" rel="noopener">' + esc(label) + '</a></h4>' +
                '<div class="arc2-meta">' + esc(h.collection_slug) + ' &middot; ' + esc(h.filename) + '</div>' +
                '<p>' + esc(h.kwic) + '</p>' +
                '</div>';
            }}).join('');
          }}

          function doFetch(url, statusEl, resultsEl, query) {{
            statusEl.textContent = 'Ricerca in corso\u2026';
            resultsEl.innerHTML = '';
            fetch(url)
              .then(function (r) {{ return r.json(); }})
              .then(function (json) {{
                var d = json.data || {{}};
                renderHits(d.hits, statusEl, resultsEl, query, d.total);
              }})
              .catch(function () {{ statusEl.textContent = 'Errore di ricerca. Riprova.'; }});
          }}

          /* ── Simple search ──────────────────────────────────────────────────── */
          if (SHOW_SIMPLE) {{
            var qSimple   = root.querySelector('.arc2-q-simple');
            var btnSimple = root.querySelector('.arc2-submit-simple');
            var stSimple  = root.querySelector('.arc2-status-simple');
            var resSimple = root.querySelector('.arc2-results-simple');

            function submitSimple() {{
              var q = qSimple.value.trim();
              if (!q) return;
              doFetch(API_BASE + '/api/v1/embed/' + SLUG + '/search?q=' + encodeURIComponent(q),
                stSimple, resSimple, q);
            }}
            btnSimple.addEventListener('click', submitSimple);
            qSimple.addEventListener('keydown', function (e) {{ if (e.key === 'Enter') submitSimple(); }});
          }}

          /* ── Advanced search ────────────────────────────────────────────────── */
          if (SHOW_ADVANCED) {{
            var qAdv   = root.querySelector('.arc2-q-adv');
            var btnAdv = root.querySelector('.arc2-submit-adv');
            var stAdv  = root.querySelector('.arc2-status-adv');
            var resAdv = root.querySelector('.arc2-results-adv');

            function submitAdv() {{
              var q = qAdv.value.trim();
              if (!q) return;
              doFetch(API_BASE + '/api/v1/embed/' + SLUG + '/advanced-search?q=' + encodeURIComponent(q),
                stAdv, resAdv, q);
            }}
            btnAdv.addEventListener('click', submitAdv);
            qAdv.addEventListener('keydown', function (e) {{ if (e.key === 'Enter') submitAdv(); }});
          }}

        }})();
    """)


async def render_widget_js(db: AsyncSession, slug: str) -> str:
    """Generate the widget.js content for the given search engine."""
    engine = await _get_embed_engine(db, slug)
    config = EmbedConfig.model_validate(engine.embed_config or {})
    return _widget_js(slug, config.mode)


# ── Inline snippet helpers (for frontend display) ─────────────────────────────

def build_widgetjs_snippet(slug: str, api_base: str) -> str:
    """Return the short <script src=...> snippet for widget.js embedding."""
    return (
        f'<div id="aracne2-{slug}"></div>\n'
        f'<script\n'
        f'  src="{api_base}/api/v1/embed/{slug}/widget.js"\n'
        f'  data-target="aracne2-{slug}">\n'
        f'</script>'
    )


def build_inline_snippet(slug: str, api_base: str, mode: str) -> str:
    """Return the self-contained inline <script> snippet."""
    widget_code = _widget_js(slug, mode)
    return (
        f'<div id="aracne2-{slug}"></div>\n'
        f'<script>\n'
        f'{widget_code}\n'
        f'</script>'
    )


# ── Embed log listing ─────────────────────────────────────────────────────────

async def list_embed_logs(
    db: AsyncSession,
    slug: str,
    page: int,
    per_page: int,
) -> PaginatedResponse[EmbedLogEntry]:
    """Return paginated embed logs for a search engine (admin endpoint)."""
    # Verify the engine exists.
    result = await db.execute(
        select(SearchEngine).where(SearchEngine.slug == slug)
    )
    engine = result.scalar_one_or_none()
    if engine is None:
        raise NotFoundError(f"Search engine '{slug}' not found")

    total_result = await db.execute(
        select(func.count()).where(
            SearchEngineEmbedLog.search_engine_id == engine.id
        )
    )
    total: int = total_result.scalar_one()

    rows_result = await db.execute(
        select(SearchEngineEmbedLog)
        .where(SearchEngineEmbedLog.search_engine_id == engine.id)
        .order_by(SearchEngineEmbedLog.requested_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = rows_result.scalars().all()

    return PaginatedResponse(
        data=[EmbedLogEntry.model_validate(r) for r in rows],
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ),
    )
