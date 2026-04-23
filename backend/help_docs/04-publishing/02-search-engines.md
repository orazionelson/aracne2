# Search Engines — standalone search portals

A **Search Engine** is a lightweight, self-contained search page that
indexes one or more collections and exposes them as a single
cross-collection search experience. It is independent from the
per-website search and can be embedded on external sites.

Typical use cases:

- A portal that searches across several collections of the same
  project.
- An embedded search box on an institutional homepage that searches
  Aracne2 content.
- A public search endpoint distinct from any single website's branding.

## Who can create Search Engines

Designer, EditorInChief, and Admin. They appear under the left sidebar
in the "Tools" section.

## Creating a Search Engine

Click **New Search Engine** and fill in:

- A title and URL slug.
- The list of collections to include (a Search Engine can span any
  number of published collections).
- Visual options: logo, colours, result template.
- Advanced search toggle (lets end-users filter by document metadata).

## Building the search page

Click **Build** to generate the static search page. Building produces:

- `index.html` — the search UI.
- `search.json.gz` — a compressed full-text index of every included
  collection's documents.
- A CSS/JS bundle for the UI.

The page can then be hosted under `/search/<slug>/` by the platform, or
downloaded as a ZIP and hosted anywhere — even offline.

## Advanced search

When enabled, the UI exposes fields for common TEI metadata:
author, title, date range, language, collection. Queries can be combined
with AND / OR operators. Non-matching documents are hidden from results
rather than dimmed, to avoid overwhelming the reader.

## Embedding the search box on an external site

From the Search Engine settings, copy the **Embed snippet** — a small
HTML+JS block that renders a branded search input on any external
webpage and forwards queries to the platform. The snippet is
origin-whitelist-gated: only origins you list in the settings can
embed.

## Clearing the cache

Results are cached for performance. If a collection changes and the
search page shows stale results, click **Clear cache** on the Search
Engine settings page to force a re-index on the next query.
