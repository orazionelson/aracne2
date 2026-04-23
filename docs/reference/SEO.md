# SEO — `robots.txt` and sitemaps

Aracne2 serves an SEO-compliant `robots.txt` and a sitemap hierarchy at the site
root so crawlers can discover the published corpus without deep-crawling the
SPA. All content is generated on request from the current DB state — no build
step, no stale artefacts.

## URL surface

```
/robots.txt                         — permissive, disallows /admin/, lists the sitemap
/sitemap.xml                        — sitemap index, points to sub-sitemaps
/sitemap-core.xml                   — public collections + documents, plus the public home when enabled
/sitemap-websites.xml               — each published website: landing + browse + visible pages
/sitemap-search-engines.xml         — opt-in; empty urlset when the toggle is off
```

All five paths are served from the backend under `/api/v1/…` and rewritten to
the root by nginx (production) and Vite (development). Crawlers always fetch the
root paths; the `/api/v1/` prefix is an implementation detail.

## What the sitemap advertises

- **Collections**: `{public_base_url}/browse/{slug}` for every collection with
  `status == 'published'` and `is_public == TRUE`.
- **Documents**: `{public_base_url}/browse/{slug}/{filename}` — one per XML file
  returned by `existdb.list_collection(slug)`. If eXist-db is momentarily
  unreachable the collection row still appears; only its document children are
  skipped.
- **Public home**: `{public_base_url}/` when `public_home_enabled == true`.
- **Websites**: each published website contributes its landing
  (`/sites/{slug}/`), its browse index (`/sites/{slug}/browse`), and every
  `WebsitePage` that is not hidden.
- **Search engines**: each engine with `build_status == done` contributes its
  built page (`/search-pages/{slug}/`) plus the advanced page when
  `advanced_search_enabled == TRUE`. Emitted only when
  `sitemap_include_search_engines == true`.

Every `<url>` carries a `<lastmod>` derived from the underlying row's
`updated_at` (or, for search engines, `last_build_at`).

## Settings

Two system settings drive the output:

| Key                                 | Default | What it gates                                                                                     |
|-------------------------------------|---------|---------------------------------------------------------------------------------------------------|
| `public_base_url`                   | `""`    | Canonical origin prefixed to every `loc`. When empty the router falls back to the request host.   |
| `public_home_enabled`               | `false` | Whether `/` appears in `/sitemap-core.xml`.                                                       |
| `sitemap_include_search_engines`    | `false` | Whether the sitemap index advertises the search-engine sub-sitemap and whether that urlset has content. Admin toggle under Settings → Homepage. |

## Deployment glue

Crawlers fetch `/robots.txt` and `/sitemap.xml` at the site root. Both
[nginx.conf](../../nginx.conf) and [frontend/vite.config.ts](../../frontend/vite.config.ts)
rewrite those paths to the backend's `/api/v1/…` siblings, so the exact same
URLs work in dev (`http://localhost:5173/robots.txt`) and prod
(`https://yourhost/robots.txt`).

## Migrations

- `0052_sitemap_include_search_engines` seeds the single new
  `system_settings` row. No schema changes, no data loss on rollback.
