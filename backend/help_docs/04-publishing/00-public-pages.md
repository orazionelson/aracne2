# Public Pages — your default public face

Even before you build a fully-featured website, every Aracne2 instance
already exposes a set of **Public Pages** that anonymous visitors can
read. They are the platform's default public face: a homepage, a
collection landing page, a per-document reader, a named-entity
browser, a bibliography page, and an optional search portal.

You don't have to set anything up for them to exist — publishing a
collection (with the public flag on) is enough. But you do have a
single admin surface, **Settings → Pagine Pubbliche** (`/admin/public-pages`,
Admin only), where every detail of how the public pages look and
behave is controlled.

This page is the map.

## What's actually public

| Path | What it is |
|---|---|
| `/` | Public homepage with platform name, logo, optional collection list and search bar |
| `/browse/<slug>` | Collection landing — title, metadata, document list (filter / sort / paginate) |
| `/browse/<slug>/<filename>` | Single document, rendered via XSLT in an iframe |
| `/browse/<slug>/bibliography` | Public bibliography for the collection (when one is marked public) |
| `/browse/<slug>/entities` | Named-entity browser scoped to the collection |
| `/search` | Embedded search portal (shows only when an admin attaches a search engine) |
| `/sitemap.xml`, `/robots.txt` | SEO surface for crawlers |

Visibility rules:

- A **collection** must be `published` AND have `is_public=true`
  before its pages appear here. Drafts and private collections stay
  hidden, even if the URL is guessed.
- The `/browse/<slug>/bibliography` page only renders when the
  collection has a `CollectionBibliography` row marked public.
- `/browse/<slug>/entities` and `/search` are always reachable when
  their data sources are public; a collection with no entities just
  shows an empty list.

## Settings → Pagine Pubbliche, top to bottom

The admin route groups every public-page knob into four panels.
Each setting is persisted as a `system_settings` row, so the value
survives across container restarts and is shared by every running
instance of the same deployment.

### 1. Logo

- **Carica immagine** — drop a PNG / JPG / SVG / WebP up to 2 MB.
  The file is stored under `<media>/logo.<ext>`; the URL is set
  automatically.
- **URL del logo** — paste any URL (relative or absolute). Useful
  when the logo lives on a CDN or you want to reuse an asset that's
  already in `frontend/public/`.
- **Ripristina default** — restore the bundled Aracne marchio.

The logo appears in the public navbar (`PublicHeader`) and in the
`<img>` next to the platform name on the public homepage.

### 2. Colore barra di navigazione

Pick any hex; the picker has eight quick swatches plus a free-form
hex input. The text colour on top of the chosen background is
**auto-derived from luminance** (WCAG sRGB formula) — slate-200 on
dark backgrounds, slate-800 on light ones — so contrast stays
readable whatever colour you pick.

A live preview at the bottom of the panel shows what the navbar
will look like with the current logo + colour combination.

### 3. Comportamento

A column of toggles controlling what the homepage and other public
pages show:

| Toggle | Default | Effect |
|---|---|---|
| **Abilita homepage pubblica** | off | Unauthenticated visitors can reach `/` (otherwise they're sent to `/login`) |
| **Abilita Search engine** *(foldable panel)* | off | Adds a "Cerca / Search" link to the public navbar that opens `/search` with the chosen built engine embedded |
| **Mostra lista collezioni** | on | Whether the homepage lists public collections |
| **Mostra barra di ricerca** | on | Search box on the homepage (filters the collection list) |
| **Abilita bottone di login** | on | Login link in the public header |
| **Propaga CSS personalizzato** | off | Your uploaded CSS is also applied to non-homepage public pages |
| **Includi i motori di ricerca nella sitemap** | off | `/sitemap.xml` advertises a sub-sitemap with each built engine's landing page |

The Search panel deserves a note: turning the toggle on without a
slug auto-selects the first available engine, so the `/search` link
never points at an empty embed URL. Picking another engine later
just updates the slug — the toggle stays on. Turning it off keeps
the slug remembered for next time.

### 4. Opzioni documento

Affordances applied to `/browse/<slug>/<filename>` (the public
document iframe). They mirror the per-website knobs the Websites
module already exposes, so deployments without any Websites still
get the same reading affordances on the core public pages.

- **Visualizzazione delle note** — radio with three modes:
  - *Fine documento* (default) — notes appear as a numbered list
    after the body of the document.
  - *Tooltip al passaggio del mouse* — hovering or clicking a marker
    reveals the note text in a popup.
  - *Pannello laterale* — clicking a marker opens a fixed side
    panel where the note is highlighted.
- **Anteprima Wikidata al passaggio del mouse** — when on, hovering
  a `persName / placeName / orgName` link with a `@ref` to Wikidata
  opens a tooltip with label + description + image. **Privacy
  note**: every hover triggers an HTTP request to Wikidata. Leave
  off if your deployment must announce third-party calls first.
- **Mostra documento in un frame** — when on (default), the
  rendered document sits in a fixed-height box with its own
  scrollbar. When off, the iframe auto-grows to its content height
  and the parent page scrolls instead — no nested scrollbar, no
  visible chrome.

### 5. Foglio di stile personalizzato

The catch-all visual override:

- Upload a `.css` file (≤ 512 KB) — applied as the last stylesheet
  on `/`, so it takes precedence over every default rule.
- Toggle **Propaga CSS personalizzato** in the Comportamento panel
  to apply the same stylesheet to `/browse/...`, `/search`, etc.
- Click **Scarica template CSS** to download a starter file with
  the right class hooks already commented in (`.ph-page`,
  `.pc-collection-header`, `.pd-breadcrumb`, `.bibliography-list`,
  …). Editing this file is the cleanest path: every selector you
  need is documented in place, and an empty rule is invisible.

## How a single setting flows to a page

The plumbing is intentionally one-way and stateless:

1. The admin clicks a toggle in `/admin/public-pages`.
2. The frontend calls `PUT /api/v1/settings/<key>` with the new
   value.
3. The backend writes the row to `system_settings` and returns.
4. The frontend re-fetches `/api/v1/settings/ui-config` so the
   shared UI store knows the new state.
5. The next page render — public or admin — reads the store and
   acts accordingly.

There is no cache to invalidate, no build to trigger. Toggles take
effect on the next page load, no exceptions.

## SEO and discoverability

Two routes worth knowing about:

- `/sitemap.xml` — auto-generated. Includes the homepage, every
  public collection landing page, and every public document.
  Adds the search-engine sub-sitemap when the corresponding toggle
  is on.
- `/robots.txt` — auto-generated. Allows everything by default;
  set `home_show_login_button=false` and the login URL is
  silently excluded so crawlers don't index a sign-in page.

JSON-LD structured data is emitted on collection and document
pages (CreativeWork + isPartOf, Person / Organization for
authors and publishers when present). You don't have to do
anything — the markup is included automatically.

## Bibliography and entity linking

- Filenames mentioned in a bibliography entry (e.g. `R1.1.1.xml`)
  are **auto-linked** to the corresponding document page when that
  document is publicly accessible. Filenames not in the visible
  set render as plain text — we never advertise a document the
  visitor cannot reach.
- The named-entity browser (`/browse/<slug>/entities`) only
  surfaces entities that have at least one occurrence in a
  published-public collection. See the
  [Named entities guide](../03-advanced/03-named-entities) for the
  full picture.

## Custom CSS — practical tips

The starter file you can download from the admin panel groups every
hookable class by surface:

- **`.ph-*`** — public homepage (PublicHomeSection)
- **`.pc-*`** — collection landing (PublicCollectionView)
- **`.pd-*`** — document viewer (PublicDocumentView)
- **`.pe-*`** — entities browser (PublicEntitiesView)
- **`.pb-*`** — bibliography (PublicBibliographyView)

A few principles that keep the override sane:

- Style the **named hooks**, not Tailwind utility classes — the
  utility classes will change between releases; the named hooks are
  contract.
- The page background is `bg-gray-50` on the layout `<main>` (not
  per-view), so a single `main { background: ... !important; }`
  rule recolours every public page at once.
- The custom CSS is loaded **after** Tailwind, so `!important` is
  rarely needed; specificity wins. Save it for true overrides.

## Public pages vs. Websites module

| Question | Public Pages | Websites module |
|---|---|---|
| One per platform, or many? | Exactly one (these are *the* public face) | One or more per collection (`/sites/<slug>/`) |
| Configured where? | Settings → Pagine Pubbliche (Admin) | Per-site editor (Designer) |
| Build step? | None — settings take effect immediately | Static / Hybrid modes need a build click |
| Custom XSLT per site? | No (one platform-wide stylesheet) | Yes (catalogue or inline) |
| URL pattern | `/`, `/browse/<slug>/...` | `/sites/<slug>/...` |
| Uses your custom CSS? | Yes (homepage; rest with the *Propaga* toggle) | No (each site has its own theme + CSS) |

In practice: keep Public Pages tidy as the universal default —
they're what a visitor sees when they hit the bare hostname. Use a
**Website** when a single collection deserves its own brand,
custom XSLT, or scholarly long-form layout.

## Troubleshooting

> The homepage shows "Login required" instead of the public list.

Turn on **Abilita homepage pubblica**. By default the platform
treats the homepage as authenticated.

> I uploaded custom CSS but only the homepage uses it.

Turn on **Propaga CSS personalizzato** in the Comportamento panel.

> The "Search" navbar item is missing.

Either the toggle is off, or the picked engine doesn't exist
anymore (deleted from `/admin/search-engines`). The setting hides
the link automatically when the slug points at nothing — re-pick
an engine, or turn the toggle off.

> A document link from a bibliography entry doesn't render as a link.

The matched filename (e.g. `R1.1.1.xml`) must exist *in the same
collection* AND the collection must be published-public. If the
document was renamed or the collection unpublished, the entry
falls back to plain text.

> The colour I picked makes my navbar text unreadable.

Don't worry — text colour is auto-derived from background luminance.
If you still see contrast trouble, try a colour on the opposite
side of the lightness curve (very dark or very light); the
auto-pick handles middle greys conservatively.
