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
- A "Deposit website on Zenodo" section in the WebsiteEditView **Deposit**
  tab — STATIC / HYBRID websites only (DYNAMIC has no static output to
  deposit). Editor picks per deposit whether to bundle the rendered tree
  into a single `<slug>.zip` (default — best for archival) or upload each
  file individually (browsable in the Zenodo Files tab). Tracked under
  the new `website_deposit` plugin_data key.

**Versions:**
- `1.0.0` — initial collection-deposit feature.
- `1.1.0` — adds website deposit (this section).

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
- A "Save website on Wayback" section in the WebsiteEditView **Deposit**
  tab — accepts all three rendering modes (Wayback only needs an HTML
  URL, which the Aracne2 server emits in every mode). Same submit →
  60-second poll → record flow as the collection path; same Refresh
  button when the SPN2 job is still pending. Manual-only (no
  auto-archive on website publish — websites get rebuilt frequently and
  one snapshot per build would be noise). Tracked under the new
  `website_archive` plugin_data key.

**Endpoints (added in 1.1.0):**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/internet-archive/websites/{slug}/status` | EiC+ | Last website-archive record, or `null` |
| POST | `/plugins/internet-archive/websites/{slug}/archive` | EiC+ | Force a fresh capture of the website's public URL |
| POST | `/plugins/internet-archive/websites/{slug}/refresh` | EiC+ | Re-poll a pending job |

**Versions:**
- `1.0.0` — initial collection-archive feature.
- `1.1.0` — adds website archive (this section).

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

## 6. `ror` — ROR affiliation lookup

| | |
|---|---|
| **Location** | `plugins/ror/` |
| **Routes** | Yes — prefix `/plugins/ror` |
| **Hooks** | None (editor-side only) |
| **min_role** | Admin (activation only; search is any authenticated user) |
| **External API** | `https://api.ror.org/v2/organizations` (public, no auth) |

Adds a "ROR" toggle to the TEI editor toolbar, next to the ORCID
button. The panel searches the Research Organization Registry by name
(or selected text), shows display names with aliases, country, and
institution types, and on "Apply" writes
``@ref="https://ror.org/..."`` on the enclosing ``<orgName>``
element.

Scope mirrors the ORCID plugin but for institutions:

- Editor-side only — this is an encoding aid. A user-level ROR
  affiliation on the ``User`` model could make sense later (parallel
  to ``User.orcid``) but is not currently a platform need.
- Applies only to ``<orgName>`` (ROR identifies institutions, not
  people or places).

Features:
- Uses ROR API **v2** — v1 was deprecated in early 2025. The v2 item
  model splits names into typed entries (`ror_display`, `alias`,
  `acronym`, `label`); the service picks the `ror_display` as the
  canonical name and surfaces the rest as aliases in the UI.
- Skips items without a usable display name rather than showing
  blank rows.
- Fail-soft: upstream hiccups (timeout, 5xx, parse error) degrade to
  an empty result list — editors never see an error banner.
- No credentials, no migration — activating the plugin is all that
  is required.

**Endpoint:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET | `/plugins/ror/search?q=...&rows=...` | User+ | Proxied public search, 30 req/min per IP |

**Settings:** none.

**Frontend:**
- Information-only config page at `/admin/plugins/ror/config` — the
  plugin has no tunables.
- Toolbar button in the TEI editor, **conditional on plugin
  activation** (`usePluginStore` check); panel component
  `RorLinkPanel.vue` mirrors `OrcidLinkPanel` in grammar.

---

## 7. `codeberg_integration` — Codeberg / Forgejo deposit

| | |
|---|---|
| **Location** | `plugins/codeberg_integration/` (uses `plugins/_lib/git_forge/` shared library) |
| **Routes** | Yes — prefix `/plugins/codeberg` |
| **Hooks** | None |
| **min_role** | Admin (config), EditorInChief (link CRUD + push), EditorInChief / Designer (website link CRUD + push) |
| **External API** | Forgejo / Gitea REST v1 (`{base_url}/api/v1/`) |

European-hosted, vendor-neutral git-forge integration. Deposits a
collection's TEI files OR a website's rendered output to a Codeberg
repository (or any self-hosted Forgejo/Gitea instance via the
per-link `base_url`) in **one commit per push** — Forgejo's batch
`POST /repos/{owner}/{repo}/contents` endpoint matches Aracne2's
"one commit always" invariant natively.

**Operations:**
1. **Push** (Aracne2 → forge): always available once the link exists.
   For collections, every TEI file in the collection lands under
   `documents/<filename>.xml`; for websites, the rendered tree
   uploads file-for-file at the repo root.
2. **Initialize** (forge → empty Aracne2 collection): one-shot import
   for migrating an existing TEI corpus. Refused once the collection
   contains any document or once the link's `initialized_at` column
   is set; XML is validated with `defusedxml` before a single byte
   reaches eXist-db, so a malformed file aborts the whole import.
   Caps: 500 files, 10 MB each.

**Per-link override**: a per-link Fernet-encrypted `pat_override`
column wins over the global `codeberg_integration_pat`. Useful when
a specific collection lives under a different owner (group / personal
namespace) whose token you don't want to share globally.

**Endpoints:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET / PUT | `/plugins/codeberg/config` | Admin | Global PAT (token_set boolean only on read) |
| GET / PUT / DELETE | `/plugins/codeberg/collections/{slug}/link` | EiC+ | CRUD the per-collection link (repo, branch, optional PAT override) |
| POST | `/plugins/codeberg/collections/{slug}/push` | EiC+ | Single-commit push of every TEI doc |
| POST | `/plugins/codeberg/collections/{slug}/initialize` | EiC+ | One-shot import (empty collection only) |
| GET / PUT / DELETE | `/plugins/codeberg/websites/{slug}/link` | Designer / EiC+ | Per-website link CRUD |
| POST | `/plugins/codeberg/websites/{slug}/push` | Designer / EiC+ | Push the rendered site (STATIC / HYBRID) |

**Settings (migration 0060–0061):**
- `codeberg_integration_pat` (sensitive)
- New tables: `codeberg_collection_links`, `codeberg_website_links`
  (each carrying `repo_owner` / `repo_name` / `branch` / `base_url` /
  `pat_override` / `last_push_*` / `initialized_*` for collections).

**Frontend:**
- Info-only config page at `/admin/plugins/codeberg_integration/config`
  (just the global PAT field — link config is per-collection / per-website).
- A "Codeberg deposit" section on `/collections/:slug` rendered by the
  shared `<ForgeCollectionSection>` component (Connect / Push /
  Initialize / Disconnect, alias of the same component instantiated
  for GitHub and GitLab too).
- A `<CodebergWebsiteSection>` in the WebsiteEditView **Deposit** tab.

**Versions:**
- `1.0.0` — Phase 1: collection push.
- `1.1.0` — Phase 2A: Initialize.
- `1.2.0` — Phase 2B: website push.

---

## 8. `github_integration` — GitHub / GitHub Enterprise deposit

| | |
|---|---|
| **Location** | `plugins/github_integration/` (uses `plugins/_lib/git_forge/`) |
| **Routes** | Yes — prefix `/plugins/github` |
| **Hooks** | None |
| **min_role** | Admin (config), EditorInChief (collection ops), Designer / EiC+ (website ops) |
| **External API** | GitHub REST v3 (`https://api.github.com/`); GitHub Enterprise Server via per-link `base_url` (rewritten to `<base>/api/v3/`) |

Same feature set as Codeberg — collection push + Initialize +
website push, per-link PAT override, Fernet-encrypted global PAT.
The adapter is structurally different because GitHub has no batch
Contents endpoint: it drives the **git data API** in four steps
(blob upload → tree composition with `base_tree` → commit → ref move
via `PATCH refs/heads/<branch>` for updates or `POST git/refs` for
the first push).

**Idiosyncrasies handled by the adapter:**
- GitHub's overloaded `403`: distinguished as `RateLimited` when the
  `x-ratelimit-remaining: 0` header is present, `Forbidden` otherwise.
- `422` on a ref `PATCH` is treated as `PushConflict` (branch moved
  under the caller; retry with fresh head).
- Auth: `Authorization: Bearer <PAT>` (works for both classic and
  fine-grained PATs).

**Settings (migration 0062):**
- `github_integration_pat` (sensitive)
- Tables: `github_collection_links`, `github_website_links` (same
  shape as Codeberg's).

**Endpoints:** identical shape to Codeberg's, prefix `/plugins/github`.

**Frontend:** identical UX shape to Codeberg's; renders via the same
`<ForgeCollectionSection>` and via `<GithubWebsiteSection>`. The
config page links to `https://github.com/settings/tokens` for the
required scopes (`repo` for classic PATs; `Contents: read & write`
for fine-grained).

**Version:** `1.0.0` — shipped with the full feature set in one commit.

---

## 9. `gitlab_integration` — GitLab deposit

| | |
|---|---|
| **Location** | `plugins/gitlab_integration/` (uses `plugins/_lib/git_forge/`) |
| **Routes** | Yes — prefix `/plugins/gitlab` |
| **Hooks** | None |
| **min_role** | Admin (config), EditorInChief (collection ops), Designer / EiC+ (website ops) |
| **External API** | GitLab REST v4 (`{base_url}/api/v4/`); self-hosted GitLab via the per-link `base_url` |

Same feature set as Codeberg / GitHub. GitLab natively exposes a
batch `POST /api/v4/projects/<id>/repository/commits` endpoint that
takes an `actions` array — closer to Forgejo's shape than GitHub's
data-API dance.

**Idiosyncrasies:**
- Project URL: GitLab requires the project as a URL-encoded
  `namespace%2Fproject` path. The adapter URL-encodes the entire
  `owner/name` field — which means **nested group paths**
  (`group/subgroup/project`) work natively if the operator stores
  the group path in `repo_owner`. The link's `repo_owner` column is
  therefore widened to `String(256)`.
- Auth: `Authorization: Bearer <PAT>` (works for both classic and
  fine-grained tokens; project-access tokens also work).
- Pagination: tree listing follows the `x-next-page` header (cap
  200 pages × 100 entries).

**Settings (migration 0063):**
- `gitlab_integration_pat` (sensitive)
- Tables: `gitlab_collection_links`, `gitlab_website_links` (with
  `repo_owner String(256)`).

**Endpoints:** identical shape, prefix `/plugins/gitlab`.

**Frontend:** identical UX; the config page links to
`https://gitlab.com/-/user_settings/personal_access_tokens` and notes
the required scope is `api` (or `write_repository` for fine-grained).

**Version:** `1.0.0` — shipped with the full feature set in one commit.

---

## 10. `dataverse_integration` — Dataverse deposit

| | |
|---|---|
| **Location** | `plugins/dataverse_integration/` |
| **Routes** | Yes — prefix `/plugins/dataverse` |
| **Hooks** | `collection.published` |
| **min_role** | Admin (config), EditorInChief (collection / website deposit) |
| **External API** | Dataverse Native API (`{base_url}/api/...`) |

Architecturally a sibling of the Zenodo plugin, targeting any
Dataverse instance — the public sandbox `https://demo.dataverse.org`
by default, or any institutional Dataverse via the configurable
`base_url`. Reuses the service-agnostic `DepositMetadata`
intermediate already produced by the Zenodo plugin's mapping module
(it was deliberately designed to be platform-neutral).

**Lifecycle (collection):**
1. On `ON_COLLECTION_PUBLISHED` (and `auto_deposit=true`), the plugin
   creates a Dataverse dataset under the configured alias, uploads
   each TEI file, and optionally publishes (DOI activates).
2. Dataverse mints the DOI **immediately on dataset creation** in
   `DRAFT` state — the badge can show the DOI from the start. But
   the DOI is *preallocated*, not yet *registered*: it does not
   resolve via `doi.org` until publish. The badge therefore links
   the DOI to the Dataverse landing page
   (`{base_url}/dataset.xhtml?persistentId=doi:<DOI>`), which always
   works regardless of state.

**Lifecycle (website):**
- Manual-only — websites get rebuilt frequently and one deposit per
  build would create churn (same precedent set with Zenodo + IA
  website features).
- STATIC and HYBRID modes only; DYNAMIC has no static output.
- Per-deposit `upload_as_zip` choice: True (default — bundle into
  `<slug>.zip`) or False (each file uploaded individually with its
  `directoryLabel` so the Dataverse Files tab shows the rendered
  tree as folders).

**Per-deposit alias override:** every deposit endpoint accepts an
`alias` field that wins over the plugin's `default_alias` setting.
Useful when one institutional installation hosts multiple
research-group Dataverses inside the same instance.

**Endpoints:**

| Method | Path | ACL | Purpose |
|--------|------|-----|---------|
| GET / PUT | `/plugins/dataverse/config` | Admin | Plugin config (token, base_url, default alias, contact, subject, publish type, two toggles) |
| GET | `/plugins/dataverse/collections/{slug}/status` | EiC+ | Last collection-deposit record |
| POST | `/plugins/dataverse/collections/{slug}/deposit` | EiC+ | Force a (re-)deposit; body accepts `alias` override |
| GET | `/plugins/dataverse/websites/{slug}/status` | EiC+ | Last website-deposit record |
| POST | `/plugins/dataverse/websites/{slug}/deposit` | EiC+ | Force a website deposit; body accepts `upload_as_zip` and `alias` |

**Settings (migration 0064):**
- `dataverse_api_token` (sensitive)
- `dataverse_base_url` (default `https://demo.dataverse.org`)
- `dataverse_default_alias` (must be set; deposit refuses when empty)
- `dataverse_auto_deposit` (bool, default `false`)
- `dataverse_auto_publish` (bool, default `false`)
- `dataverse_default_subject` (default `Arts and Humanities` from
  Dataverse's controlled subject vocabulary)
- `dataverse_contact_name` / `dataverse_contact_email` (Dataverse
  refuses datasets without a contact email; falls back to
  `admin_email` when empty)
- `dataverse_publish_type` (`major` / `minor` / `updatecurrent`,
  default `major`)
- No new tables — per-deposit alias override travels in the request
  body and is recorded inside the `plugin_data` payload.

**Frontend:**
- Config page at `/admin/plugins/dataverse_integration/config` with
  the subject dropdown populated from Dataverse's controlled vocab.
- `<DataverseCollectionSection>` on `/collections/:slug`, with a
  "Use a different alias for this deposit…" link revealing the
  override input. The DOI is shown for both draft and published
  states; a draft-only caveat line spells out the resolver behaviour.
- `<DataverseWebsiteSection>` in the WebsiteEditView **Deposit** tab.

**Version:** `1.0.0`.

---

## 11. `evt` — EVT 2 viewer feed

| | |
|---|---|
| **Location** | `plugins/evt/` (was `plugins/_native/evt/` until v2.0.0) |
| **Routes** | Yes — prefix `/public/collections` |
| **Hooks** | None |
| **min_role** | User |

Exposes two **public** endpoints that the EVT 2 viewer container
proxies:
- `GET /public/collections/{slug}/evt-config` → EVT-shaped JSON
  (one record per file in the collection).
- `GET /public/collections/{slug}/documents/{filename}/raw` → raw
  TEI bytes for a given file.

The viewer UI itself is not part of this plugin — it lives in a
separate nginx container activated via the `evt` Docker Compose
profile. This plugin only provides the data feed.

**Why it's now non-native:** EVT is specific to deployments that
expose editions through the EVT viewer; not every deployment wants
that. Activating from `/admin/plugins` mounts the routes; the
`/collections/:slug/read` page shows a friendly "Viewer not enabled
on this installation" fallback when the plugin is inactive.

**Settings:** `evt_enabled` (bool, system_settings) is now
AND-ed with the plugin's activation state in the public
`UiConfigResponse` so dead buttons never appear on public pages.

**Versions:**
- `1.0.0` — shipped as a native plugin.
- `2.0.0` — converted to non-native; opt-in activation; routes
  unmount when the plugin is inactive.

---

## 12. Authority lookup plugins (compact catalogue)

A family of plugins that turn the editor's selected text inside a
TEI element into an authoritative `@ref` URL by querying an external
authority service. They share a common shape — Editor-side panel
opened from the toolbar, no auth (mostly), one POST endpoint per
service — so a per-plugin breakdown would be repetitive. Reference
table:

| Slug | Targets `@ref` on | Authority | Notes |
|---|---|---|---|
| `wikidata` | persName, placeName, orgName, etc. | Wikidata | No auth; uses `wbsearchentities` |
| `orcid` | persName | ORCID | No auth; public search |
| `ror` | orgName | ROR (Research Org Registry) | No auth |
| `viaf` | persName | VIAF | No auth |
| `geonames` | placeName | GeoNames | Username via `geonames_username` system setting (default `aracne`; override per-deployment) |
| `crossref_lookup` | bibl / biblStruct | CrossRef | Polite-pool email via `crossref_contact_email` |
| `gnd` | persName, placeName, orgName | GND via lobid.org | No auth |
| `cerl` | persName, placeName, orgName | CERL Thesaurus | No auth |
| `peripleo` | placeName | Pelagios Peripleo | No auth; aggregates Pleiades + iDAI + others |
| `getty_aat` | term | Getty AAT | SPARQL via `vocab.getty.edu`; no auth |
| `openalex` | bibl / biblStruct | OpenAlex | Polite-pool email via `openalex_contact_email` |
| `trismegistos` | persName, placeName, bibl | Trismegistos | **ID resolver only** (no free-text search — TM doesn't publish one). Three kinds (person / place / text) + optional source for partner-ID reverse lookup (HGV → TM, DDBDP → TM, …) |

Each ships with:
- A toolbar button in the TEI editor, conditional on plugin activation
  (`usePluginStore` check).
- A panel component (`<XxxLinkPanel>`) that handles the search/resolve
  + apply-as-`@ref` flow.
- Fail-soft HTTP client with `httpx.MockTransport` test coverage.

**Trismegistos rebuild (v2.0.0)**: originally written against a
speculative `api/v3/search` endpoint that doesn't exist publicly.
Rebuilt in v2.0.0 against the **documented public ID-resolver
endpoints** (`dataservices/texrelations/<id>`,
`dataservices/georelations/<id>`) with no auth required. The panel
is now an ID-resolver UX (kind + ID + optional source) rather than a
search box. Migration 0059 dropped the now-unused
`trismegistos_api_key` row.

---

## 13. `help` — In-app help browser

| | |
|---|---|
| **Location** | `plugins/help/` |
| **Routes** | Yes — prefix `/plugins/help` |
| **min_role** | User |

Renders the markdown files under `backend/help_docs/` as HTML
(sanitised with `bleach`) and exposes a search endpoint that the
in-app Help drawer queries. The help corpus itself is the
documentation editors see without leaving the platform; new chapters
are added by dropping markdown files under `backend/help_docs/`.

---

## Summary

| Slug | Purpose | Trigger | External auth |
|---|---|---|---|
| `zenodo_deposit` | Deposit collections + websites on Zenodo (returns DOI on publish) | `collection.published` + manual; manual for websites | Zenodo PAT (Fernet) |
| `internet_archive` | Capture collections + websites on Wayback Machine | `collection.published` + manual + refresh; manual for websites | S3-style keys (Fernet) |
| `dataverse_integration` | Deposit collections + websites on Dataverse (DOI on creation) | `collection.published` (auto-deposit toggle) + manual; manual for websites | Dataverse API token (Fernet) |
| `codeberg_integration` | Push collections + websites to Codeberg / Forgejo; one-shot Initialize for collections | Manual | Codeberg PAT (Fernet, global + per-link override) |
| `github_integration` | Push collections + websites to GitHub / GHE; one-shot Initialize for collections | Manual | GitHub PAT (Fernet, global + per-link override) |
| `gitlab_integration` | Push collections + websites to GitLab; one-shot Initialize for collections | Manual | GitLab PAT (Fernet, global + per-link override) |
| `evt` | Feed the EVT 2 viewer with config JSON + raw TEI | Public HTTP requests from the EVT container | None |
| `zotero_import` | Import Zotero library into bibliography | Manual pull (preview + commit) | Zotero read-only API key (Fernet) |
| `wikidata` / `orcid` / `ror` / `viaf` / `gnd` / `cerl` / `peripleo` / `getty_aat` / `openalex` / `trismegistos` | Resolve TEI selection → authority URI / biblStruct | Editor-side panel | Mostly none; OpenAlex/CrossRef use polite-pool email; GeoNames uses a shared username |
| `crossref_lookup` | Resolve DOI → `<biblStruct>` | Editor-side | Polite-pool contact email (plain) |
| `help` | In-app help browser | User-side drawer | None |

Each plugin is self-contained: its directory, its settings, its
`plugin_data` namespace, its admin config page. Uninstalling a plugin
means deleting the directory + restarting the backend + optionally
removing its `plugin_data` and `system_settings` rows. No code
outside the plugin directory has to change.

The four forge plugins (Codeberg, GitHub, GitLab) and the Dataverse
plugin share a common shape but are deliberately separate: each
owns its own credentials, its own per-link state, its own config
page. The shared `plugins/_lib/git_forge/` library carries the
adapter Protocol + push/Initialize orchestrator + token resolution
helpers — so adding a fourth git forge or a third Dataverse-style
DOI repository is mostly a serialiser + adapter swap.

## See also

- [`PLUGINS.md`](PLUGINS.md) — plugin subsystem internals (loader,
  hook registry, native plugins catalogue, how to write a new
  non-native plugin from scratch).
- [`FUTURE_IDEAS.md`](../FUTURE_IDEAS.md) — proposed but not-yet-shipped
  non-native plugins (GROBID PDF → TEI, DataCite DOI, GitHub
  integration, Matomo/Plausible analytics, …).
