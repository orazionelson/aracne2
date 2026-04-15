# Styling the Public Homepage

This document lists every descriptive CSS class present on the public
homepage component (`frontend/src/components/PublicHomeSection.vue`).
Each element carries at least one semantic class alongside its Tailwind
utility classes, so custom stylesheets can target specific areas without
relying on brittle structural selectors.

---

## Page structure

| Class | Element | Description |
|---|---|---|
| `ph-page` | `<div>` | Outermost page wrapper (full viewport height, gray background) |
| `ph-header` | `<header>` | Top navigation bar (brand color background) |
| `ph-main` | `<main>` | Content area (centered, max-width constrained) |

---

## Header

| Class | Element | Description |
|---|---|---|
| `ph-logo` | `<a>` | Logo + platform name link (links to `/`) |
| `ph-logo-img` | `<img>` | Platform logo image (hidden when no URL is configured) |
| `ph-site-name` | `<span>` | Platform name text |
| `ph-login` | `<span>` | Login link wrapper (hidden when `home_show_login_button` is off) |

---

## Search bar

Rendered only when the `home_show_search` setting is enabled.

| Class | Element | Description |
|---|---|---|
| `ph-search` | `<div>` | Search section wrapper |
| `ph-search-form` | `<form>` | Search form |
| `ph-search-input` | `<input>` | Text input field |
| `ph-search-btn` | `<button>` | Submit button |
| `ph-search-reset` | `<button>` | Reset/clear button (visible only when a search is active) |

---

## Collection section

Rendered only when the `home_show_collections` setting is enabled.

| Class | Element | Description |
|---|---|---|
| `ph-stats` | `<p>` | Collection count line (e.g. "142 collections") |
| `ph-loading` | `<p>` | Loading indicator shown while data is fetched |
| `ph-no-results` | `<p>` | Message shown when a search returns no matches |
| `ph-empty` | `<p>` | Message shown when there are no published collections |

---

## Recent additions block ("Ultime aggiunte")

Rendered on page 1 when not searching and at least one collection exists.

| Class | Element | Description |
|---|---|---|
| `last-add` | `<section>` | Section wrapper for the recent-additions block |
| `last-add-title` | `<h2>` | Section heading |
| `last-add-grid` | `<div>` | Three-column card grid |
| `last-add-card` | `<div>` | Individual collection card |

---

## Full collection list

| Class | Element | Description |
|---|---|---|
| `search-results-title` | `<h2>` | Heading shown when displaying search results |
| `all-collections-title` | `<h2>` | Heading shown when displaying the full collection list |
| `collection-list` | `<ul>` | Ordered list of all collections |
| `collection-item` | `<li>` | Single collection row |

---

## Collection metadata (shared between cards and list items)

| Class | Element | Description |
|---|---|---|
| `col-title` | `<h2>` / `<h3>` | Collection title |
| `col-desc` | `<p>` | Short description (two-line clamp) |
| `col-meta` | `<div>` | Metadata row (author, publisher, year, date) |
| `col-author` | `<span>` | Author name |
| `col-publisher` | `<span>` | Publisher name (list view only) |
| `col-year` | `<span>` | Publication year |
| `col-date` | `<span>` | Publication date (list view only) |
| `col-actions` | `<div>` | Action button row |

---

## Action buttons (shared between cards and list items)

| Class | Element | Description |
|---|---|---|
| `btn-browse` | `<a>` | "Browse" — links to the public collection view |
| `btn-evt` | `<a>` | "View in EVT" — shown only when EVT is enabled and the collection has exactly one document |
| `btn-bibliography` | `<a>` | "Bibliography" — shown only when the collection has a public bibliography |
| `btn-entities` | `<a>` | "Named entities" — shown only when the entity count is > 0 |
| `btn-website` | `<a>` | "Website" — external link, shown only when a safe URL is configured |

---

## Search hit snippets

Rendered inside a collection row when the search matched document content.

| Class | Element | Description |
|---|---|---|
| `doc-hits` | `<ul>` | List of document matches |
| `doc-hit` | `<li>` | Single document match row |
| `doc-hit-link` | `<a>` | Clickable link to the matched document |
| `hit-filename` | `<span>` | Document filename |
| `hit-snippet` | `<span>` | Excerpt from the matched document content |

---

## Pagination

Rendered when there is more than one page and no active search.

| Class | Element | Description |
|---|---|---|
| `ph-pagination` | `<nav>` | Pagination navigation wrapper |
| `pagination-prev` | `<button>` | "Previous page" button |
| `pagination-page` | `<button>` | Individual page number button |
| `pagination-ellipsis` | `<span>` | Ellipsis separator between non-consecutive page numbers |
| `pagination-next` | `<button>` | "Next page" button |

---

## Settings that affect rendering

The following system settings (configurable under **Admin → Settings → Homepage**)
determine which sections are rendered:

| Setting key | Default | Effect |
|---|---|---|
| `public_home_enabled` | `false` | Enables the public homepage entirely |
| `home_show_collections` | `true` | Shows/hides the collection section and search results |
| `home_show_search` | `true` | Shows/hides the search bar (`ph-search` block) |
| `home_show_login_button` | `true` | Shows/hides the `ph-login` element in the header |
