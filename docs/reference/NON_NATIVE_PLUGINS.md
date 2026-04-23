# Non-native plugins

Aracne2 ships a small catalogue of **non-native** plugins — optional,
per-deployment opt-in integrations with external services. They live
in [`backend/app/plugins/<slug>/`](../../backend/app/plugins/) (no
leading underscore — that prefix is reserved for the always-active
native plugins) and follow a uniform scaffolding:

```
plugins/<slug>/
├── __init__.py
├── plugin.py        # Plugin class + hook registration (if any)
├── service.py       # HTTP client / pure mapping / orchestration
├── router.py        # Admin config + per-collection endpoints
├── schemas.py       # Pydantic request/response
├── config.py        # runtime settings loader (optional)
└── tests/
    ├── __init__.py
    ├── conftest.py  # re-exports shared fixtures from app/tests/conftest.py
    └── test_*.py
```

This document describes each non-native plugin: what it does, its
settings, its endpoints, and how it surfaces in the admin and editor
UIs. For the plugin subsystem itself (loader, hook registry, native
vs non-native semantics, how to write a new plugin) see
[`PLUGINS.md`](PLUGINS.md).

## Activation model

1. A plugin directory sits in the repo at `backend/app/plugins/<slug>/`.
   The backend plugin loader discovers it at every start-up and upserts
   a row in the `plugins` table.
2. Non-native plugins always land in `status = inactive`. An Admin
   toggles them to `active` from `/admin/plugins`.
3. Activation alone is not enough to mount the plugin's HTTP routes —
   `include_router` runs only during FastAPI's lifespan startup, so
   the admin has to restart the backend after flipping activation.
   The frontend config page surfaces a "restart required" error when
   a plugin is freshly active but its routes are still unmounted.
4. Deactivating a plugin hides its UI (see each plugin's Frontend
   section below) but leaves `plugin_data` rows and `system_settings`
   rows intact — re-activation picks up the previous state.

## Shared conventions

- **Credentials are Fernet-encrypted** in `system_settings` via
  `SENSITIVE_KEYS` in [`app/core/encryption.py`](../../backend/app/core/encryption.py).
  Plaintext never round-trips to the API.
- **Admin config page** is registered in the frontend plugin registry
  at [`components/plugins/registry.ts`](../../frontend/src/components/plugins/registry.ts)
  and reached from `/admin/plugins` via the "Configure" link on an
  active plugin row. The URL is `/admin/plugins/<slug>/config`.
- **Per-collection state** lives in `plugin_data` under
  `entity_type="collection"`, keyed on a plugin-owned key (e.g.
  `"deposit"` for Zenodo, `"archive"` for Internet Archive,
  `"import"` for Zotero). See
  [`services/plugin_data.py`](../../backend/app/services/plugin_data.py).
- **Fail-soft on upstream hiccups**: every plugin's HTTP client
  degrades gracefully on timeout / 5xx / parse errors. The editor
  sees an empty result list or a translated error banner, never a
  500.
- **ACL convention**: Admin for config CRUD; EditorInChief (or User+
  for pure lookup panels) for the editorial endpoints.
- **Rate limiting**: outbound-proxy endpoints (CrossRef, ORCID) are
  capped via the platform's shared slowapi limiter.

---

## 1. `zenodo_deposit` — Zenodo Deposit

| | |
|---|---|
| **Location** | `plugins/zenodo_deposit/` |
| **Routes** | Yes — prefix `/plugins/zenodo-deposit` |
| **Hooks** | `collection.published` |
| **min_role** | Admin (config), EditorInChief (status / manual re-deposit) |
| **External API** | Zenodo (InvenioRDM) `/api/records` |

Deposits a published collection on [Zenodo](https://zenodo.org) — bundles the
collection's TEI documents and metadata and returns a DOI when the
`auto_publish` toggle is enabled (otherwise leaves the record as a draft for
manual review on Zenodo).

The plugin targets the **new Zenodo (InvenioRDM) API**, not the legacy
`/api/deposit/depositions` endpoints. This yields a richer metadata model
(creators split into given/family with ORCID + affiliations; live
resource-type vocabulary; `rights` array referencing InvenioRDM's license
vocabulary; structured `related_identifiers`).

**Deposit flow:**
1. `POST /api/records` — create draft with full InvenioRDM metadata.
2. `POST /api/records/{id}/draft/files` — declare each filename.
3. `PUT /api/records/{id}/draft/files/{key}/content` — stream the TEI bytes.
4. `POST /api/records/{id}/draft/files/{key}/commit` — commit.
5. If `zenodo_auto_publish=true`, `POST /api/records/{id}/draft/actions/publish`
   mints the DOI; otherwise the record stays as a draft.

Features:
- Sandbox (`sandbox.zenodo.org`) and production endpoints, selected from the UI.
- Fernet-encrypted API token stored as `zenodo_api_token` in `system_settings`
  (added to `SENSITIVE_KEYS`).
- **Live resource-type vocabulary**: the config panel pulls Zenodo's
  `GET /api/vocabularies/resourcetypes` via the proxied
  `/plugins/zenodo-deposit/resource-types` endpoint and renders it as a
  grouped dropdown ("Publication / Book", "Image / Photo", "Dataset", …).
  Falls back to a hard-coded list when Zenodo is unreachable.
- **Per-collection resource type override**: `collections.zenodo_resource_type`
  (nullable) lets an EiC pick a different InvenioRDM vocabulary id for
  one specific collection; NULL inherits the global setting.
- **Per-collection ZIP bundling**: `collections.zenodo_upload_as_zip`
  (bool, default false) bundles every TEI doc into one `{slug}.zip`
  instead of uploading per-file.
- Per-collection deposit record stored in `plugin_data` (deposit id, DOI,
  record URL, status, submitted_at). Re-deposit is idempotent on failures
  and skipped on already-successful deposits unless forced.
- Metadata is built by the plugin's own `mapping.py` module via a reusable
  `DepositMetadata` intermediate — so a future DataCite or HAL plugin can
  plug in a different serialiser without re-extracting from the ORM.
- License vocabulary id mapped from the seeded Creative Commons licenses
  (`cc-by-4.0`, `cc-by-sa-4.0`, `cc0-1.0`, …).
- **ORCID propagation**: when a creator name matches an Aracne2 user
  with `users.orcid` set, the plugin emits a
  `person_or_org.identifiers: [{scheme: "orcid", …}]` entry.

**Endpoints:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/zenodo-deposit/config` | Admin | Current non-sensitive config (token is never returned; only `token_set` bool) |
| PUT | `/plugins/zenodo-deposit/config` | Admin | Partial update of any config field |
| GET | `/plugins/zenodo-deposit/resource-types` | Admin | Proxied InvenioRDM resource-type vocabulary, normalised for the UI |
| GET | `/plugins/zenodo-deposit/collections/{slug}/status` | EiC+ | Last deposit record for a collection, or `null` |
| POST | `/plugins/zenodo-deposit/collections/{slug}/deposit` | EiC+ | Force a fresh deposit attempt |

**Settings:**

- `zenodo_api_token` (sensitive) — personal access token with scopes
  `deposit:actions` and `deposit:write`
- `zenodo_base_url` — `https://sandbox.zenodo.org` or `https://zenodo.org`
- `zenodo_default_community` — optional community slug
- `zenodo_auto_publish` — bool
- `zenodo_access` — `open` / `restricted` (InvenioRDM access model; embargo
  is not exposed in the MVP because it requires an `until` date UI)
- `zenodo_resource_type` — InvenioRDM vocabulary id, default
  `publication-other`
- `public_base_url` — canonical public origin used to link each deposit back
  to the collection page on this site (also usable by other plugins)

**Migrations:**
- `0047_zenodo_deposit_settings.py` — seeds the initial rows
- `0048_zenodo_rdm_migration.py` — renames `zenodo_publication_type` →
  `zenodo_resource_type` (mapping legacy enum values to InvenioRDM
  vocabulary ids) and `zenodo_access_right` → `zenodo_access`
  (folding `embargoed`/`closed` into `restricted`)
- `0049_collection_zenodo_resource_type.py` — per-collection override
- `0050_collection_zenodo_upload_as_zip.py` — per-collection ZIP flag

**Frontend:**
- Dedicated config page at `/admin/plugins/zenodo_deposit/config`.
- A deposit badge next to the status pill in `/collections/:slug`, with a
  "Re-deposit on Zenodo" button for EditorInChief and above.
- Per-collection "Deposito Zenodo" section (EiC+) with resource-type
  dropdown + "Upload as single ZIP" toggle.

---

## 2. `internet_archive` — Internet Archive (Wayback Machine)

| | |
|---|---|
| **Location** | `plugins/internet_archive/` |
| **Routes** | Yes — prefix `/plugins/internet-archive` |
| **Hooks** | `collection.published` |
| **min_role** | Admin (config), EditorInChief (status / manual archive / refresh) |
| **External API** | Save Page Now 2 (`https://web.archive.org/save/`) |

Submits a published collection's public URL to the Wayback Machine
and records the resulting snapshot URL on the collection. A small green
"Archived on Wayback" badge appears next to the Zenodo DOI badge.

**Lifecycle:**
1. On `ON_COLLECTION_PUBLISHED` (and `auto_archive=true`), the plugin
   builds `{public_base_url}/browse/{slug}` and `POST`s it to SPN2.
2. SPN2 returns a `job_id`; the plugin writes a `pending` record to
   `plugin_data` immediately so the UI has something to show even if
   the backend restarts mid-capture.
3. It then polls `GET /save/status/{job_id}` every 5s for up to 60s.
4. On a terminal response (`success` or `error`), the record is
   upgraded. On timeout the record stays `pending` — the editor can
   click "Refresh archive status" on the collection page to re-poll.

Features:
- Fernet-encrypted `internet_archive_access_key` and
  `internet_archive_secret_key` in `system_settings`.
- `auto_archive` toggle (default `true`) — turn off to archive only
  via the manual button on each collection.
- Idempotent on success: re-publishing a collection that already has a
  successful snapshot skips the call. Force re-archive from the UI or
  `POST .../collections/{slug}/archive`.

**Endpoints:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/internet-archive/config` | Admin | Current non-sensitive config (both keys masked; only `*_set` booleans exposed) |
| PUT | `/plugins/internet-archive/config` | Admin | Partial update of any config field |
| GET | `/plugins/internet-archive/collections/{slug}/status` | EiC+ | Last archive record for a collection, or `null` |
| POST | `/plugins/internet-archive/collections/{slug}/archive` | EiC+ | Force a fresh capture attempt |
| POST | `/plugins/internet-archive/collections/{slug}/refresh` | EiC+ | Re-poll a pending SPN2 job |

**Settings (migration 0051):**
- `internet_archive_access_key` (sensitive)
- `internet_archive_secret_key` (sensitive)
- `internet_archive_auto_archive` (bool, default `true`)

**Frontend:**
- Dedicated config page at `/admin/plugins/internet_archive/config`.
- Archived-on-Wayback badge next to the Zenodo badge on
  `/collections/:slug`, with a green "Archive" / amber "Refresh"
  button for EditorInChief and above.

---

## 3. `zotero_import` — Zotero Import

| | |
|---|---|
| **Location** | `plugins/zotero_import/` |
| **Routes** | Yes — prefix `/plugins/zotero-import` |
| **Hooks** | None (manual pull) |
| **min_role** | Admin (config), EditorInChief (preview / import) |
| **External API** | Zotero Web API v3 (`https://api.zotero.org`) |

Pulls bibliographic entries from a configured Zotero group or user
library into a collection's bibliography. Complements the AI
Bibliobuilder (which normalises entries already present in the
corpus) and the CrossRef resolver (which resolves one DOI at a time)
by importing external curated bibliography in bulk.

Unlike Zenodo and Internet Archive, this plugin does **not** register
a lifecycle hook. Zotero imports are pulled manually by an EiC from
the collection page — there is no automatic trigger.

**Flow:**
1. Admin registers a read-only Zotero API key + library type (`user`
   or `group`) + numeric library id in the plugin config.
2. EiC opens a collection's bibliography panel, clicks "Import from
   Zotero". The plugin fetches **every** item in the library and
   diffs against a per-collection "already imported" list stored in
   `plugin_data.imported_zotero_keys`.
3. Preview modal shows the diff; editor ticks which new items to
   import (pre-selected by default).
4. On confirm, the selected items are mapped to TEI biblStructs and
   appended to the collection's **current** `<listBibl>`, producing a
   new CollectionBibliography version. The set of imported Zotero
   keys is updated so subsequent runs skip these items.

Features:
- Fernet-encrypted `zotero_api_key`.
- Paginates the Zotero library transparently via `Link: rel="next"`
  (RFC 5988); no manual page-count config.
- Filters out Zotero's non-bibliographic item types (`note`,
  `attachment`, `annotation`) before mapping.
- De-duplicates by stable Zotero item `key` — re-running an import
  after the editor edits a generated biblStruct in the Aracne2 editor
  will **not** re-import it.
- Maps Zotero creators with `firstName`/`lastName` into
  `<persName><surname><forename>`; `name`-only creators (organisations
  or single-token creators) emit `<orgName>`. Editors and translators
  on book sections are placed on the host monograph.

**Endpoints:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/zotero-import/config` | Admin | Current non-sensitive config |
| PUT | `/plugins/zotero-import/config` | Admin | Partial update of any config field |
| POST | `/plugins/zotero-import/collections/{slug}/preview` | EiC+ | Diff the library vs previously-imported keys |
| POST | `/plugins/zotero-import/collections/{slug}/import` | EiC+ | Persist a new bibliography version with the selected items |

**Settings (migration 0053):**
- `zotero_api_key` (sensitive) — read-only Zotero API key
- `zotero_library_type` — `user` or `group`
- `zotero_library_id` — numeric library id
- `zotero_api_base` — optional override for tests or mirrors

**Frontend:**
- Config page at `/admin/plugins/zotero_import/config`.
- "Import from Zotero" button + modal inside the "Saved
  bibliographies" panel on `/collections/:slug`, rendered only when
  the plugin is active.

---

## 4. `orcid` — ORCID lookup

| | |
|---|---|
| **Location** | `plugins/orcid/` |
| **Routes** | Yes — prefix `/plugins/orcid` |
| **Hooks** | None (editor-side only) |
| **min_role** | Admin (activation only; search is any authenticated user) |
| **External API** | `https://pub.orcid.org/v3.0/expanded-search/` (public, no auth) |

Adds an "ORCID" toggle to the TEI editor toolbar, next to the
Wikidata button. The panel searches the public ORCID registry by name
(or selected text), shows display names + affiliations, and on "Apply"
writes ``@ref="https://orcid.org/0000-..."`` on the enclosing
``<persName>`` element.

Scope is deliberately narrow:

- Editor-side only — attaching an ORCID to an **Aracne2 user** is a
  core ``User.orcid`` field (see the user manual) because downstream
  consumers (Zenodo, LOD) read from there and would otherwise need
  cross-plugin data snooping.
- Applies only to ``<persName>`` (ORCID identifies people, not places
  or organisations).

Features:
- Uses the ``expanded-search`` endpoint so names and institutions
  land in the hit list without N+1 round-trips.
- Fail-soft: upstream hiccups degrade to an empty result list so
  editors never see an error banner.
- No credentials, no migration — activating the plugin is all that
  is required.

**Endpoint:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/orcid/search?q=...&rows=...` | User+ | Proxied public search, 30 req/min per IP |

**Settings:** none.

**Frontend:**
- Information-only config page at `/admin/plugins/orcid/config` —
  the plugin has no tunables.
- Toolbar button in the TEI editor, **conditional on plugin
  activation** (`usePluginStore` check); panel component
  `OrcidLinkPanel.vue` mirrors `WikidataLinkPanel` in grammar.

---

## 5. `crossref_lookup` — CrossRef DOI resolver

| | |
|---|---|
| **Location** | `plugins/crossref_lookup/` |
| **Routes** | Yes — prefix `/plugins/crossref-lookup` |
| **Hooks** | None (editor-side only) |
| **min_role** | Admin (config); EditorInChief (lookup) |
| **External API** | `https://api.crossref.org/works/{doi}` (public, no auth) |

Adds a "DOI" toggle to the TEI editor toolbar. The panel fetches the
canonical CrossRef record for a pasted DOI and produces a
ready-to-insert TEI ``<biblStruct>``. Complements the AI
``tei_bibl_inline`` prompt: deterministic, not subject to
hallucination, keyed on the opaque DOI.

Features:
- Three TEI shapes driven by CrossRef's ``type``:
  ``journal-article`` / ``proceedings-article`` → ``journalArticle``;
  ``book`` / ``monograph`` / ``reference-book`` / ``edited-book`` →
  ``book``; ``book-chapter`` / ``book-section`` / ``reference-entry``
  → ``bookSection``. Everything else collapses to ``type="other"``.
- Extracts year from the most reliable CrossRef date field
  (``published-print`` > ``published-online`` > ``issued`` >
  ``created``).
- ``xml:id`` generated as ``bib_{surname_ascii_slug}_{year}``, with
  a 3-word title fallback and unicode surname ASCII-slugging so ids
  stay stable across locales.
- DOI prefix tolerance: accepts bare DOI, ``doi:…``, and
  ``https://doi.org/…``.
- "Polite pool" identification: contact email goes into the
  ``User-Agent`` ``mailto:`` token so CrossRef can reach the operator
  if the service misbehaves. Falls back to the platform ``admin_email``
  when the plugin's own ``crossref_contact_email`` is empty.

**Endpoints:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/crossref-lookup/config` | Admin | Current non-sensitive config (contact email + platform fallback) |
| PUT | `/plugins/crossref-lookup/config` | Admin | Update the contact email |
| GET | `/plugins/crossref-lookup/lookup?doi=…` | EiC+ | Resolve a DOI to a biblStruct (30 req/min) |

**Settings (migration 0055):**
- `crossref_contact_email` — polite-pool contact email; empty falls
  back to `admin_email`.

**Frontend:**
- Config page at `/admin/plugins/crossref_lookup/config`.
- Toolbar button in the TEI editor, **conditional on plugin
  activation** via `usePluginStore`.
- Panel component `CrossrefPanel.vue` (editor UI).

---

## Summary

| Slug | Purpose | Trigger | External auth |
|---|---|---|---|
| `zenodo_deposit` | Deposits collections on Zenodo; returns DOI | `collection.published` + manual | Zenodo PAT (Fernet) |
| `internet_archive` | Captures collections on Wayback Machine | `collection.published` + manual + refresh | S3-style keys (Fernet) |
| `zotero_import` | Imports Zotero library into bibliography | Manual pull (preview + commit) | Zotero read-only API key (Fernet) |
| `orcid` | Resolves `<persName>` → ORCID URI | Editor-side | None |
| `crossref_lookup` | Resolves DOI → `<biblStruct>` | Editor-side | Polite-pool contact email (plain) |

Each plugin is self-contained: its directory, its settings, its
`plugin_data` namespace, its admin config page. Uninstalling a plugin
means deleting the directory + restarting the backend + optionally
removing its `plugin_data` and `system_settings` rows. No code
outside the plugin directory has to change.

## See also

- [`PLUGINS.md`](PLUGINS.md) — plugin subsystem internals (loader,
  hook registry, native plugins catalogue, how to write a new
  non-native plugin from scratch).
- [`FUTURE_IDEAS.md`](../FUTURE_IDEAS.md) — proposed but not-yet-shipped
  non-native plugins (GROBID PDF → TEI, DataCite DOI, ROR
  affiliations, GitHub integration, …).
