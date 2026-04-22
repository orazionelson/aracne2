# Future Ideas

Exploratory ideas and long-horizon features that are worth considering but have
no committed timeline. Unlike `DEFERRED.md` (which tracks architectural decisions
for features already in scope), entries here are **speculative**: they may never be
implemented, or may be reconsidered as the product evolves.

Each entry describes the idea, the motivation, the open questions, and any
prerequisite that would need to be in place first.

### Priority legend

| Label | Meaning |
|---|---|
| 🔴 High | Strong fit with project goals; likely to be needed; relatively clear implementation path |
| 🟡 Medium | Useful but not urgent; depends on growth in usage or contributor base |
| 🟢 Low | Technically interesting but low immediate impact or high complexity |
| 🔵 To discuss | Value or direction unclear; needs stakeholder input before scoping |

---

## 1. CLI import/export tool 🔴 High

A standalone command-line tool (`aracne-cli`) for bulk operations outside the web UI.

**Motivation**
Large editorial projects often start with an existing corpus of TEI files on a
filesystem or in a zip archive. Manually uploading hundreds of documents through
the web UI is impractical. Similarly, full collection exports for archiving or
migration need to work headlessly.

**Scope**
```
aracne-cli import --collection my-corpus --dir ./tei_files/ --host https://cms.example.com
aracne-cli export --collection my-corpus --format zip --output ./export.zip
aracne-cli validate --dir ./tei_files/ --schema tei_all
```

**Implementation options**
- Python CLI using `click` or `typer`, distributed as a PyPI package.
- Thin wrapper around the existing REST API (no direct DB access).
  Authentication via a long-lived API token (new token type, separate from JWT sessions).
- Can be developed independently of the CMS release cycle once the API is stable.

**Open questions**
- Long-lived API tokens require a new token type in the `sessions` table
  (or a dedicated `api_tokens` table) with explicit scopes.
- Conflict resolution on import: skip, overwrite, or rename duplicates?

**Prerequisites**
- Document CRUD API (Phase 05+)
- API token authentication (new feature, not currently planned)

---

## 2. Non-native plugin: GitHub Integration 🔴 High

Connect a collection to a GitHub repository and allow EditorInChiefs to push
documents to GitHub and, exclusively for empty collections, perform a one-time
initialization from an existing GitHub repository.

### Motivation and use cases

Many digital humanities projects already use GitHub to store and version TEI XML
corpora. A GitHub integration plugin would allow Aracne2 to act as both a live
editing environment (eXist-db as the operational store) and a versioned archive
(GitHub as the durable, public, diff-visible record). Concrete benefits:

- **Transparent version history**: every editorial state is a git commit — human-readable,
  diff-able, and permanently linked to a commit SHA.
- **CI/CD hooks via GitHub Actions**: a push can trigger downstream automation —
  ODD compilation, static site generation, XSLT validation, Zenodo archival.
- **Open-access publication**: for projects that publish their data as open corpora,
  the GitHub repo is the citable, harvestable artifact (alongside OAI-PMH exposure
  already provided by Aracne2).
- **Backup layer**: a GitHub push after publication is an off-site snapshot independent
  of both eXist-db and any infrastructure backup.
- **Corpus import**: a TEI project that already lives on GitHub can be imported into
  Aracne2 in one step, without manual file-by-file upload.

### Source of truth and data flow

**eXist-db is always and unconditionally the source of truth.** This constraint is
enforced at the system level, not by user discipline.

The plugin exposes two operations with **strictly asymmetric rules**:

```
Push:       eXist-db → GitHub   always available; collection may contain any number of documents
Initialize: GitHub → eXist-db   available ONLY when the collection has zero documents
```

**Initialize from GitHub** is a one-shot operation. Once the collection contains at
least one document — whether imported from GitHub or created manually — the
Initialize button is permanently disabled and the endpoint returns HTTP 409.
From that point, the only allowed direction is push. This makes it impossible to
accidentally overwrite a live collection with GitHub content.

The intended workflows are:

- **New project, hosted on Aracne2 from day one**: create collection → work in
  Aracne2 → push to GitHub periodically or on publish. Initialize is never used.

- **Existing GitHub corpus, migrating to Aracne2**: create an empty collection →
  connect to the GitHub repo → Initialize (one time) → all documents are now in
  eXist-db → from this point, push only.

There is no recurring bidirectional sync and no merge operation. These are
deliberate design exclusions, not deferred features.

### Plugin classification and directory

Non-native; installed and activated by Admin. Located at:

```
backend/app/plugins/github_integration/
├── __init__.py
├── plugin.py          ← loader entry point; registers hooks
├── router.py          ← HTTP endpoints
├── service.py         ← push / initialize logic; GitHub API calls
├── models.py          ← ORM model for github_collection_links table
└── schemas.py         ← Pydantic v2 request/response schemas
```

### Storage: dedicated `github_collection_links` table

Per-collection configuration is structured data, not simple key-value pairs.
A dedicated table is cleaner and more queryable than the global `plugins.config`
JSONB column, which is intended for installation-wide plugin settings rather than
per-entity records. This plugin also provides the first concrete justification for
the `plugin_data` generic table described in `DEFERRED.md` item 3 — though the
dedicated table approach is preferred here for type safety and queryability.

**Proposed schema:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID` PK | |
| `collection_id` | `UUID FK → collections.id` | `ON DELETE CASCADE`; `UNIQUE` — one link per collection |
| `repo` | `VARCHAR(256)` | `owner/repo-name` format, e.g. `username/dante-tei` |
| `branch` | `VARCHAR(128)` | Default `main` |
| `path_prefix` | `VARCHAR(512)` | Subdirectory inside the repo where XML files live; default `/` |
| `pat_encrypted` | `TEXT` | GitHub PAT encrypted with `app/core/encryption.py` |
| `auto_push_on_publish` | `bool` | If true, `ON_COLLECTION_PUBLISHED` hook triggers an automatic push |
| `last_push_at` | `DateTime(tz)` | Timestamp of the last successful push |
| `last_push_sha` | `VARCHAR(64)` | Commit SHA of the last push |
| `initialized_at` | `DateTime(tz)` | Timestamp of the one-time initialize operation (null if never run) |
| `initialized_from_sha` | `VARCHAR(64)` | Commit SHA from which the collection was initialized |
| `connected_by` | `UUID FK → users.id` | Who connected the collection; `SET NULL` on user delete |
| `connected_at` | `DateTime(tz)` | |

The rename of `last_pull_*` to `initialized_*` reflects the semantic: this was a
one-time initialization event, not a recurring pull.

### Credentials: Personal Access Token (PAT)

The plugin uses a GitHub **fine-grained Personal Access Token** scoped to the
target repository with `Contents: Read and Write` permission. The PAT is entered
when connecting a collection, immediately encrypted with `app/core/encryption.py`
(symmetric key derived from `JWT_SECRET`), and stored in `pat_encrypted`. The
plaintext PAT is never logged or returned by any API endpoint after saving.

On connection, the plugin validates the PAT by calling `GET /repos/{owner}/{repo}`
and verifying HTTP 200, rejecting the connection if the token is invalid or the
repo is inaccessible.

**GitHub OAuth App** (full three-leg OAuth flow) is a more secure alternative with
higher rate limits but requires registering an OAuth App with GitHub. Noted here
as a future upgrade path; out of scope for the initial implementation.

### GitHub API strategy: tree-based commits (no local git clone)

All git operations are implemented via the **GitHub REST API**. No `git` binary,
no `gitpython` dependency, no local working directory, no persistent volume.

**Push** — uses the low-level git objects API to produce a single atomic commit:

1. `GET /repos/{owner}/{repo}/git/ref/heads/{branch}` — fetch current HEAD SHA.
2. Export all `.xml` documents from eXist-db for the collection.
3. For each file: `POST /repos/{owner}/{repo}/git/blobs` — create a blob with
   base64-encoded UTF-8 content.
4. `POST /repos/{owner}/{repo}/git/trees` — create a tree assembling all blobs
   at `path_prefix`.
5. `POST /repos/{owner}/{repo}/git/commits` — create a commit with the user-supplied
   message, pointing to the new tree and the current HEAD as parent.
6. `PATCH /repos/{owner}/{repo}/git/refs/heads/{branch}` — advance the branch ref.

The commit is linear on top of the current remote HEAD. If another user has pushed
to the repo in the meantime, the new commit is simply their linear successor — the
Aracne2 content replaces the files at `path_prefix` without a merge, which is correct
because eXist-db is the source of truth. The GitHub history preserves both states.

**Initialize** — one-time import from GitHub to an empty eXist-db collection:

1. Verify the collection has zero documents (count query on eXist-db). If not: HTTP 409.
2. `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` — list all files;
   filter for `.xml` extensions under `path_prefix`.
3. For each file: `GET /repos/{owner}/{repo}/contents/{path}` — fetch and base64-decode.
4. Import each XML file into eXist-db via the existing collection document service
   (same code path as a manual upload). If any import fails, **roll back**: delete
   all files imported so far in this operation, leaving the collection empty again.
5. On full success: write `initialized_at` and `initialized_from_sha` to the link row.

The rollback in step 4 ensures the operation is atomic from the user's perspective:
the collection is either fully populated or still empty — never partially filled.
A partially filled collection would block a retry since the emptiness check in step 1
would fail.

### Operations and endpoints

All endpoints are mounted under `/api/v1/github`.

| Method | Path | ACL | Description |
|--------|------|-----|-------------|
| `POST` | `/github/collections/{collection_id}/connect` | `[EiC+]` | Connect to a GitHub repo; validates PAT; fails if already connected |
| `DELETE` | `/github/collections/{collection_id}/connect` | `[EiC+]` | Disconnect; removes link row; does not touch GitHub content |
| `GET` | `/github/collections/{collection_id}/status` | `[E+]` | Link config, last push timestamp, last SHA (clickable link to GitHub), whether Initialize is still available |
| `POST` | `/github/collections/{collection_id}/push` | `[EiC+]` | Push all collection XML to GitHub; body: `{ "message": "commit message" }` |
| `POST` | `/github/collections/{collection_id}/initialize` | `[EiC+]` | One-time import from GitHub; HTTP 409 if collection is not empty |

The endpoint name `initialize` (not `pull`) is intentional: it signals a
non-recurring, destructive-if-wrong operation that is only valid once.

### Auto-push on publish (hook integration)

When `auto_push_on_publish` is true, the plugin registers a handler on
`ON_COLLECTION_PUBLISHED`. On receiving the event:

1. Commit message: `"Auto-push: collection published — {timestamp}"`.
2. Run the push flow as a background `asyncio.create_task`.
3. Update `last_push_at` / `last_push_sha` on success; log the error via structlog
   on failure without blocking the publication state transition.

### Media files (images)

Binary media files (images referenced in `<facsimile>`) are excluded from push by
default. GitHub handles binaries poorly without Git LFS, and TEI image files can be
large. The plugin operates only on `.xml` files.

A future `push_media` flag could extend the scope to include `/media/` via Git LFS
pointers, but this requires Git LFS to be enabled on the repository and is not part
of the initial scope.

### Frontend UI

A new **"GitHub" tab** in the Collection detail view, visible to Editor+ and
interactive for EditorInChief+.

**Not connected:**
```
┌─────────────────────────────────────────────────────────┐
│  GitHub Integration                                      │
│  ─────────────────────────────────────────────────────  │
│  This collection is not connected to a GitHub repository.│
│                                                          │
│  [ Connect to GitHub ]                                   │
└─────────────────────────────────────────────────────────┘
```

**Connect dialog** (modal):
- Repository: `owner/repo-name`
- Branch: `main` (default)
- Path in repo: `/` (default)
- Personal Access Token: password field (never shown again)
- Auto-push on publish: toggle
- [ Connect ] [ Cancel ]

**Connected — collection empty (Initialize available):**
```
┌─────────────────────────────────────────────────────────┐
│  GitHub Integration                    [ Disconnect ]    │
│  ─────────────────────────────────────────────────────  │
│  Repository:  username/dante-tei  (branch: main)        │
│  Last push:   —                                          │
│  Auto-push on publish: ON                               │
│                                                          │
│  [ Push to GitHub ↑ ]                                    │
│                                                          │
│  ┌─ Initialize from GitHub ──────────────────────────┐  │
│  │ The collection is empty. You can import documents  │  │
│  │ from the connected repository one time.            │  │
│  │ After import, this option will no longer be        │  │
│  │ available.                          [ Initialize ] │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Connected — collection has documents (Initialize disabled):**
```
┌─────────────────────────────────────────────────────────┐
│  GitHub Integration                    [ Disconnect ]    │
│  ─────────────────────────────────────────────────────  │
│  Repository:  username/dante-tei  (branch: main)        │
│  Last push:   2026-04-16 14:32 UTC  →  a3f7c12  ↗       │
│  Initialized: 2026-04-14 09:10 UTC  from  8e2b901        │
│  Auto-push on publish: ON                               │
│                                                          │
│  [ Push to GitHub ↑ ]                                    │
└─────────────────────────────────────────────────────────┘
```

The Initialize panel disappears entirely once `initialized_at` is set or the
document count is > 0. The Push button is always visible when connected.

**Push dialog**: commit message field, character count, [ Push ] button.
**Initialize dialog**: light informational notice ("N XML files will be imported
from branch `main`. This collection is currently empty."), [ Confirm Initialize ] button.
No scary overwrite warning needed — the emptiness guarantee makes the operation safe.

### Open questions

1. **Rate limits**: the GitHub REST API allows 5,000 authenticated requests per hour.
   Pushing 500 documents uses ~503 API calls (500 blob POSTs + tree + commit + ref).
   Mitigation for large collections: diff the remote tree against eXist-db before
   pushing — send only changed files by comparing blob SHAs (GitHub provides SHA
   in the tree listing). This is a significant optimisation worth implementing from
   the start if the expected collection size is > 200 documents.

2. **GitHub Apps vs. PAT**: GitHub Apps have higher rate limits (15,000 req/hour)
   and narrower permission scopes, but require registering an OAuth App per Aracne2
   installation. Noted as a future upgrade path if PAT rate limits become a problem.

3. **Repository visibility**: the `status` endpoint returns the repo name, visible
   to all Editor+ users. For projects with private repos, verify that this is
   acceptable before deploying.

4. **Encoding**: XML is stored in eXist-db as UTF-8. The GitHub blob API requires
   base64 encoding. Verify the round-trip for multi-byte characters (Greek, Arabic,
   Hebrew, etc.) which are common in TEI critical editions.

5. **Git history continuity on reconnect**: if a collection is disconnected and
   reconnected to the same repo, the next push creates a commit on top of the
   existing remote history (step 1 always reads the current HEAD fresh). The
   `initialized_*` columns are reset on reconnect so that, if the collection is
   also emptied and recreated, Initialize becomes available again.

### Prerequisites

| Prerequisite | Status | Notes |
|---|---|---|
| Plugin system (`PluginBase`, `PluginLoader`) | ✅ Phase 01b | Already implemented |
| Collection document count query on eXist-db | Phase 05+ | Needed for the emptiness check in Initialize |
| Collection document export from eXist-db | Phase 05+ | Needed to enumerate files for push |
| `app/core/encryption.py` (PAT encryption) | ❓ Verify | Check if symmetric encryption module exists; add if not |
| `github_collection_links` Alembic migration | ❌ Not implemented | New table — own migration file |
| `asyncio.create_task` for background auto-push | ✅ Pattern exists | Already used by `named_entities` plugin |
| Frontend: GitHub tab in CollectionDetailView | ❌ Not implemented | ~160 lines Vue; Initialize panel conditionally rendered |

### Trigger for implementation

First explicit request from an EditorInChief or Admin who manages a collection that
is also maintained as a GitHub repository, or when a project arrives with an existing
GitHub corpus that needs to be imported into Aracne2.

*Added: 2026-04-16*

---

## 3. Automated bibliography enrichment via DOI / ISBN lookup 🔴 High

When an Editor enters a bibliographic reference in the document, the system can
fetch structured metadata from CrossRef (DOI) or Open Library (ISBN) and
populate the entry automatically.

**Motivation**
Manual entry of bibliographic metadata is error-prone and time-consuming.
Auto-population from authoritative sources improves data quality and editor
productivity.

**Scope**
- Frontend: a lookup field in the bibliography management panel.
  The Editor pastes a DOI or ISBN; the frontend calls the backend.
- Backend: `GET /bibliography/lookup?doi=10.xxx/yyy` or `?isbn=978...`
  The backend proxies the request to CrossRef / Open Library, parses the
  response, and returns a normalized `BibliographyEntry` schema.
- The Editor reviews the auto-filled form and saves.

**Open questions**
- Rate limits and caching: CrossRef allows free API access but throttles at
  ~50 req/s. Cache lookup results in PostgreSQL or Redis to avoid duplicate calls.
- Fallback: if CrossRef returns nothing (conference papers, grey literature),
  fall back to manual entry — do not block the workflow.
- Data model: the normalized entry should map cleanly to TEI `<biblStruct>`.

**Prerequisites**
- Bibliography management endpoints (Phase 05+)
- `httpx` already in stack — no new dependency needed for the proxy call

---

## 4. Public reader statistics and analytics 🔴 High

Track how published documents and collections are accessed by public readers,
with an aggregated dashboard for EditorInChiefs and Admins.

**Motivation**
Scholarly editors and funders often need evidence of readership to justify project
resources. Basic analytics (views per document, geographic distribution,
search query frequency) provide this evidence without relying on third-party
tracking services.

**Scope**
- Page view counter per document (incremented on public `GET /pub/...` access)
- Aggregated daily/monthly views stored in a `view_stats` table
  (no individual user tracking — privacy-first design)
- Search query log (anonymized: IP hashed, no session linkage)
- Dashboard: top documents, views over time, most common search terms

**Privacy constraints**
- No individual-level tracking — only aggregate counts
- IP addresses hashed before storage (already in place for audit log)
- Stats retention configurable via `system_settings` (default: 12 months)
- No third-party analytics services — all data stays on the platform

**Open questions**
- Time series storage: plain `view_stats` table with daily aggregation rows,
  or TimescaleDB / PostgreSQL partitioning for larger deployments?
- Bot filtering: distinguish crawler traffic from human readers
  (User-Agent heuristics + rate-based detection).

**Prerequisites**
- Public rendering layer (Phase 06+)
- `system_settings` retention policy (already partially implemented)

---

## 5. Gamification / contributor leaderboard 🟡 Medium

A lightweight engagement layer for large distributed transcription projects:
track individual Editor contributions (documents transcribed, words encoded,
corrections approved) and display an optional leaderboard.

**Motivation**
Crowd-sourced transcription projects (manuscript digitization campaigns,
large corpora) depend on volunteer engagement. Visible contribution metrics
have been shown to improve retention and motivation in similar projects
(e.g., Zooniverse, Transkribus crowdsourcing).

**Scope**
- A `contributions` table tracking: `user_id`, `event_type`, `document_id`,
  `word_count_delta`, `timestamp`.
- Events: document created, document saved (delta), review approved.
- Public or semi-public leaderboard: opt-in per user (GDPR: visibility is
  a user preference, not a default).
- Frontend: a `ContributorsView.vue` showing top contributors with avatars,
  document counts, and word counts — linked from the public website if enabled.

**Open questions**
- Word count computation: TEI word count requires parsing the XML and counting
  text nodes within `<body>` — an XQuery job, not a simple row count.
- Fairness: a short document with dense TEI encoding takes longer than a long
  document of plain text. Raw word count is a poor proxy for effort.
- This feature is only meaningful for projects with many contributors.
  It should be a plugin, not a core feature.

**Prerequisites**
- Document CRUD (Phase 05+)
- Public rendering layer (Phase 06+)
- Plugin system hooks: `document.saved`, `review.approved` (already planned)

---

## 6. Mobile companion app 🟢 Low

A lightweight read-only mobile client (iOS + Android) for Editors and
EditorInChiefs to review documents and approve publication requests on the go.

**Motivation**
Editorial workflows often require quick approvals or status checks from people
who are away from their desks. A native app with push notifications would reduce
turnaround time for review cycles.

**Scope**
Read-only access is sufficient for most use cases:
- Browse assigned collections and their publication state
- Open documents in a rendered view (HTML from XSLT, not the raw XML editor)
- Approve / reject publication requests (simple state transition, one HTTP call)
- Receive push notifications for events: document submitted for review, comment added

Full XML editing on mobile is out of scope — the CodeMirror editor is not
practical on a touch screen.

**Open questions**
- Framework: native (Swift + Kotlin) vs. cross-platform (Flutter, React Native,
  Capacitor wrapping the existing Vue SPA)?
- Capacitor is the lowest-friction option given the existing Vue 3 frontend.
  The SPA already uses responsive Tailwind CSS; a dedicated mobile view layer
  could be added without forking the codebase.
- Push notifications require a server-side delivery layer (APNs + FCM).
  This is a non-trivial addition to the backend (new `device_tokens` table,
  new `notification_dispatcher` channel).

**Prerequisites**
- WebSocket or SSE notification delivery (DEFERRED item 9) must be in place, or
  alternatively a polling-friendly `/notifications` endpoint (already exists).
- The publication workflow (Phase 05+) must be operational.

---

## 7. Collaborative real-time editing 🟢 Low

Allow multiple Editors to work simultaneously on the same XML document with
conflict-free merging and cursor presence awareness.

**Motivation**
Large TEI transcription projects often involve teams where different editors
handle different sections of the same document. Sequential lock-based editing
creates bottlenecks; real-time collaboration removes them.

**Scope**
- Operational Transformation (OT) or CRDT-based conflict resolution on XML text
- Cursor presence: each connected user's cursor position shown in the editor
- Awareness panel: list of who is currently editing the document

**Open questions**
- XML-aware OT/CRDT is significantly harder than plain text (CodeMirror's
  built-in Yjs integration works for text; XML structure requires extra care).
- Requires a persistent WebSocket connection per open document, which conflicts
  with simple horizontal scaling (needs sticky sessions or a shared state layer).
- eXist-db has no built-in real-time collaboration support — the document would
  need to be reconstructed and saved to eXist-db on each significant checkpoint.

**Prerequisites**
- WebSocket layer (DEFERRED item 9)
- Document versioning strategy (DEFERRED item 7)
- Async task queue for durable saves (DEFERRED item 1)

---

## 8. Secret management — beyond plain-text `.env` 🟢 Low

Aracne2 currently stores all secrets (database passwords, JWT secret, API keys)
in a plain-text `.env` file. In production this file is protected by filesystem
permissions (`chmod 600`), and it is excluded from git via `.gitignore`. This is
adequate for most self-hosted deployments.

For environments with stricter security requirements or compliance obligations,
the following approaches are worth considering in order of increasing complexity:

**Docker Secrets (Docker Swarm)**
Docker Swarm can inject secrets as in-memory tmpfs files (`/run/secrets/<name>`)
rather than environment variables. Secrets are never written to disk on worker
nodes and are not visible in `docker inspect`. Requires migrating from
`docker compose` (single-node) to Docker Swarm (cluster). Pydantic Settings
would need to read secret values from files rather than environment variables
(supported via `secrets_dir` in `pydantic-settings`).

**HashiCorp Vault**
A dedicated secret management server with audit logging, secret rotation,
fine-grained access policies, and dynamic credentials (Vault can generate
short-lived PostgreSQL users on demand). High operational overhead; suitable
for enterprise deployments or multi-team environments. The backend would need
a Vault client at startup to fetch secrets before constructing `Settings`.

**Cloud-native secret managers (AWS Secrets Manager, GCP Secret Manager,
Azure Key Vault)**
Managed services that integrate natively with cloud IAM. Zero infrastructure
overhead but create a cloud provider dependency. Suitable when Aracne2 is
deployed on a cloud VM or container platform. Pydantic Settings can be extended
with a custom settings source to fetch from these services at boot.

**When to consider**
The current `chmod 600` approach is sufficient unless: (a) the server is shared
with untrusted OS users, (b) there are formal compliance requirements (SOC 2,
ISO 27001, HIPAA), or (c) secret rotation must be automated without redeploying
the stack.

*Added: 2026-04-17*

---

## 9. Glossary and index generation from named entities 🔵 To discuss

Automatically generate a structured glossary or index of persons, places, and
works from the named entity index, rendered as a navigable section of the
public website.

**Motivation**
Critical editions traditionally include an index of names and a glossary of terms.
Aracne2 already tracks named entities in PostgreSQL and links them to TEI elements
(`<persName>`, `<placeName>`, `<title>`) — generating an index from this data
is a natural extension.

**Scope**
- Public endpoint: `GET /pub/websites/{slug}/index/persons`
  Returns all persons referenced in the published documents of that website,
  with links to the passages where they appear.
- Same for places, organizations, works.
- Frontend: an `IndexView.vue` with alphabetical navigation (A–Z jump links)
  and a detail panel showing bio/geo data from the entity record plus
  all document occurrences.

**Open questions**
- Occurrence linking requires a pre-built index: either stored in PostgreSQL
  at document-save time, or computed at render time via XQuery.
  XQuery is simpler but slower for large corpora.
- The entity detail panel could optionally fetch external data
  (VIAF, GeoNames, Wikidata) to enrich the display — but this requires
  network calls at render time and introduces external dependencies.

**Prerequisites**
- Named entity management (Phase 05+)
- Public rendering layer (Phase 06+)
- Full-text search / XQuery occurrence index (DEFERRED item 8)

---

## 10. TEI-to-DOCX / TEI-to-PDF export 🔵 To discuss

Allow Editors to export a document or collection as a Word `.docx` file or PDF
for non-technical stakeholders or traditional publishers.

**Motivation**
Not all collaborators work in XML or read rendered HTML. Providing a
well-formatted Word export bridges the gap between the digital edition
environment and traditional editorial workflows.

**Scope**
- `GET /collections/{slug}/documents/{doc_id}/export?format=docx`
- `GET /collections/{slug}/documents/{doc_id}/export?format=pdf`
- Backend pipeline: TEI XML → XSLT → intermediate format → final format
  - DOCX: `python-docx` or `pandoc` (via subprocess)
  - PDF: `weasyprint` (HTML → PDF via CSS) or `pandoc` (via LaTeX → PDF)

**Open questions**
- Fidelity: scholarly TEI markup (`<app>`, `<rdg>`, `<note type="critical">`)
  does not map cleanly to Word or PDF without significant XSLT investment.
  The export will always be a simplified representation.
- `pandoc` (if used via subprocess) is a system dependency not in the current
  stack. `weasyprint` is a Python package but adds ~20 MB to the image.
- Export of large collections: must be async (DEFERRED item 1).

**Prerequisites**
- Document CRUD and XSLT rendering (Phase 05+)
- Async task queue for large exports (DEFERRED item 1)

---

## 11. Fuzzy string matching via Apache Commons Text in XQuery 🔵 To discuss

Install the **Apache Commons Text Functions** library (version 1.12.0, compatible
with eXist-db 6.0.0+) from the eXist-db Package Manager. This exposes string
similarity and distance functions (Levenshtein, Jaro-Winkler, Cosine, etc.)
directly in XQuery via the `http://exist-db.org/xquery/commons-text` namespace.

**Motivation**
Some text-processing tasks that currently run in Python could benefit from being
pushed down into XQuery, where they execute closer to the data:
- Fuzzy deduplication of named entities (e.g. "Manzoni" vs "A. Manzoni")
  during entity extraction or reindex passes
- Candidate matching when linking a TEI `<persName>` to an existing authority record
- Spelling variant grouping in fulltext search result post-processing

**Current state**
Named entity deduplication and merge are handled at the Python application layer.
eXist-db Lucene fulltext already covers the main search use case. This library
would be an optimisation or a convenience, not a requirement.

**When to consider**
If a future XQuery needs string similarity logic and the Python round-trip
(fetch results → compute → re-query) becomes a measurable bottleneck, or if an
XQuery-native merge/dedup pipeline is designed as part of a large corpus import.

**Installation**
One-time operation via the eXist-db Dashboard → Package Manager. No Aracne2
code changes required — the functions become available in all XQuery files
once installed.

**Open questions**
- The library is maintained by the eXist-db project; verify it is still
  actively updated before depending on it in production XQuery.
- Benchmark against Python `rapidfuzz` (already available if needed) to
  determine whether the XQuery approach is actually faster for the workloads
  Aracne2 produces.

*Added: 2026-04-17*

---

## 12. TEI-specialised local model via LoRA fine-tuning 🟡 Medium

Fine-tune a small local model (e.g. `llama3.1:8b`, `qwen2.5:7b`) on
TEI-specific instruction/output pairs to produce a model that internalises
P5 conventions. Goal: shorter prompts, more consistent output, no
per-token cost, and quality closer to remote providers on extractive
and format-heavy tasks.

### Motivation

Local models in the 7–14B range are the pragmatic option for
privacy-sensitive or air-gapped deployments (via Ollama), but they lag
behind Claude / GPT-4 on complex TEI reasoning out of the box. Heavy
prompts with P5 spec snippets and few-shot examples mitigate this at
inference cost. A domain-specialised adapter captures the same knowledge
in the weights.

### Realistic path

1. **Dataset (~1–10k pairs)** — the editorial corpus produced inside
   Aracne2 is itself the natural supervision signal: every (draft,
   validated output) pair is a training example. Synthetic augmentation
   from a strong model (Claude) is possible but must be validated
   against the schema to avoid hallucinated conventions.
2. **Training** — LoRA/QLoRA adapter with `unsloth`, `axolotl`, or
   `llama-factory` on a GPU (RTX 4090-class or cloud rental). Hours,
   not days.
3. **Packaging** — merge or keep the adapter separate, convert to GGUF
   with `llama.cpp`, wrap in an Ollama Modelfile:

   ```
   FROM llama3.1:8b
   ADAPTER ./aracne-tei.gguf
   ```

   `ollama create aracne-tei -f Modelfile` and point `ai_ollama_model`
   at the new tag.

### Open questions

- **Dataset size and quality**: below ~1k high-quality pairs the
  adapter is probably not worth the effort. What is the minimum
  viable dataset?
- **Base model choice**: Qwen tends to handle Italian / multilingual
  better; Llama is more widely supported in the toolchain. Probably
  train two adapters and compare.
- **Evaluation harness**: held-out TEI tasks with measurable metrics
  (schema validity, element coverage, fidelity to source). Without it,
  iteration is blind.
- **Distribution**: ship the model publicly (community reuse) vs
  per-installation (respects client data).
- **Licensing**: Llama 3.x license restricts some redistribution
  scenarios; Qwen 2.5 is Apache-like for most sizes. Verify before
  distribution.

### Prerequisites

- RAG prototype (entry #??? / under discussion) already in place — so
  we can measure the adapter's marginal gain on top of retrieval.
- At least ~1k validated documents in the platform corpus.
- Access to a GPU for training (cloud is fine; training is one-off).
- Evaluation harness defined (even a small one).

### Trigger

Consider this when **all** of the following hold:

- Local inference is in regular use in at least one installation;
- Prompt engineering and RAG have hit a visible quality or latency
  plateau;
- The corpus has grown enough to support a supervised dataset;
- A concrete use case (airgapped deployment, high-volume extractive
  task) justifies the engineering cost.

Until then, prompt engineering and RAG give a better effort/result
ratio and should be exhausted first.

*Added: 2026-04-22*

---

## 13. End-to-end AI evaluation harness 🟡 Medium

Automated test suite that exercises every native AI prompt against a live
provider, scores the output against golden expectations, and gates
regressions in the seed library.

### Motivation

Today's `test_ai_prompts.py` only does structural smoke tests: it verifies
seed idempotency and that every `{variable}` in a prompt body is covered by
`context_vars`. It does not verify that the model actually produces correct
TEI for a given input — because running real LLMs in CI would require
provider credentials, cost money, and yield non-deterministic output.

As the prompt library grows (and especially once RAG is in place), we need
a way to catch quality regressions: a small template tweak can quietly
break a downstream task. The harness provides that signal.

### Realistic scope

- Fixture: a curated dataset of ~10–20 (prompt\_slug, context, expected)
  triples per native prompt. Inputs and expected outputs live in
  `backend/app/tests/fixtures/ai/<slug>/` as plain XML files.
- Runner: a pytest plugin that, when a `--ai-eval` flag is passed, invokes
  `stream_completion` against a configured provider and scores the
  generated output with metrics:
  - schema validity (against the collection's TEI schema — already available);
  - structural match (element names, attribute presence);
  - fuzzy text similarity to the expected output (rapidfuzz / bleurt-lite).
- Scoring: per-prompt score plus aggregate. Fail CI if a PR drops the
  score below a threshold.
- Providers covered: Gemini and Ollama initially (the providers the
  maintainer has keys / local access for); OpenAI and Anthropic later
  if shared test credentials are available.

### Open questions

- **Non-determinism**: LLM output varies between runs. Threshold-based
  pass/fail with score margins is the usual answer; fuzzy matching + a
  wide enough band avoids flakiness.
- **Cost**: paid providers (OpenAI / Anthropic) cost per-token. A full
  harness over 50 prompts × 10 fixtures × 2 providers is non-trivial.
  Keep the suite opt-in (`--ai-eval` flag) and run it outside the default
  CI; schedule a weekly full run.
- **Reference output curation**: who writes the golden TEI? Initial set
  from a human editor; later pulled from the editorial corpus once
  enough validated documents exist (same dataset as the LoRA fine-tuning
  track in entry #12).
- **Provider skew**: the same prompt produces different (but both valid)
  TEI across providers. Score structure rather than exact text.

### Prerequisites

- Stable native prompt library (the current 10 seeded prompts are a fine
  baseline).
- RAG operational (entry in the roadmap above) — the harness should
  evaluate prompts with retrieved context, not bare prompts, to reflect
  production behaviour.

### Trigger

Consider this when:
- The prompt library grows past ~15 native prompts and the risk of silent
  regressions from template edits becomes real;
- Multiple providers are actively used and cross-provider consistency
  matters;
- Shared test credentials / a budget for paid-provider calls is available.

Until then, the structural smoke tests (rendering + variable coverage)
are sufficient.

*Added: 2026-04-22*

---

## 14. SPARQL endpoint over the published corpus 🟢 Low

Expose the published TEI corpus as a SPARQL 1.1 endpoint, so external
aggregators and researchers can run federated queries against Aracne2
alongside DBpedia, Wikidata, VIAF and other LOD sources.

### Motivation

The LOD track lands inbound entity linking to Wikidata (step 1),
schema.org JSON-LD in public pages (step 2), and content-negotiated
RDF export (step 3) in the near term. A SPARQL endpoint is the logical
step 4: it unlocks structured querying (e.g. "every document in the
corpus that mentions a person also mentioned by Petrarch's *Rerum
vulgarium fragmenta*") without requiring the consumer to first
harvest the whole RDF dump.

### Realistic scope

- **Triplestore** — Apache Jena Fuseki, Oxigraph (Rust, lightweight),
  or Blazegraph. Oxigraph is the smallest footprint and has an
  embedded mode; Fuseki is the most widely deployed in the academic
  LOD ecosystem.
- **Population** — a background job converts each published TEI
  document (and its linked entities) to RDF using the step-3 mapping
  and writes the triples into the store. Reindex on publish event.
- **Public endpoint** — `/sparql` with a YASGUI-style query editor
  on the website; read-only SPARQL SELECT/ASK, no UPDATE from the
  public surface.
- **Named graphs per collection** so a consumer can scope queries
  to a specific edition.

### Open questions

- **Triplestore pick**: Oxigraph (zero-ops, embed) vs Fuseki (full
  features, more moving parts)?
- **Performance vs freshness**: rebuild on publish (correct but
  slow on big corpora) vs periodic reindex (stale windows)?
- **Auth posture**: fully public SELECT (default), token-gated for
  heavy queries, or IP-based throttle?
- **Observability**: log top queries? Count unique originating
  SPARQL sources? Privacy implications for academic usage.

### Prerequisites

- **Step 1 — inbound entity linking**: done (Wikidata adapter wired,
  named-entity model carries `@ref`).
- **Step 2 — JSON-LD in public pages**: planned (LOD.2).
- **Step 3 — RDF content negotiation with TEI-Ontology mapping**:
  planned (LOD.3). The SPARQL store consumes the same mapping output.
- **Corpus size**: makes sense when at least one installation has a
  published corpus large enough (≳ 100 documents) that flat RDF dump
  harvesting becomes inconvenient for consumers.

### Trigger

Consider this when:
- RDF export (LOD.3) is in use by a real aggregator or harvester;
- a partner institution asks for federated SPARQL queries against
  the Aracne2 corpus;
- at least one installation has ≥ 100 published TEI documents with
  meaningful `@ref` entity linking.

Until then, the dump-based RDF export from LOD.3 covers the same
use cases with an order of magnitude less operational burden.

*Added: 2026-04-22*

---

*Last updated: 2026-04-22*
