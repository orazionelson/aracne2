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

## 2. ~~Non-native plugin: GitHub Integration~~ ✅ Shipped

The GitHub Integration plugin shipped in 2026-04 along with parallel
Codeberg and GitLab plugins, all built on the shared
`plugins/_lib/git_forge/` abstraction. Each forge plugin supports
collection push, website push, one-shot Initialize for empty
collections (forge → eXist-db), and a per-link PAT override on top
of the global plugin PAT. Self-hosted Forgejo / GHE / GitLab work
via the per-link `base_url`.

See [NON_NATIVE_PLUGINS.md §7 (Codeberg)](./reference/NON_NATIVE_PLUGINS.md),
[§8 (GitHub)](./reference/NON_NATIVE_PLUGINS.md), and
[§9 (GitLab)](./reference/NON_NATIVE_PLUGINS.md) for the canonical
specs. The detailed plan that drove implementation is preserved
below for historical context.

---

### Original plan (2026-04-16, shipped 2026-04-24)

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

### Digital-sovereignty variant: Codeberg integration

A parallel plugin targeting [Codeberg](https://codeberg.org), the non-profit,
European-hosted code forge run by Codeberg e.V. and powered by
[Forgejo](https://forgejo.org/) (a community fork of Gitea). The motivation is
explicitly **digital sovereignty**: institutions — especially in the EU public
and academic sectors — increasingly prefer, or are required, to host critical
repositories on European infrastructure that is free of vendor lock-in and
independent of US-domiciled platforms. A Codeberg option makes Aracne2 a
credible choice for those deployments without asking editors to learn a
different workflow.

Architecturally the work is close to a rename. Forgejo's REST API is
API-compatible with Gitea and broadly mirrors the GitHub endpoints the plugin
already needs (create/update file blobs, list contents of a repo, read the
current HEAD, create a commit). The sensible path is therefore to refactor the
GitHub plugin as it is being built — or shortly after — into a thin
`git_forge` abstraction with two adapters:

```
backend/app/plugins/
├── github_integration/      ← existing target
├── codeberg_integration/    ← new adapter, thin wrapper over the abstraction
└── _lib/git_forge/          ← shared push/initialize logic, forge-agnostic
```

Same Admin → activate → per-collection link model; same storage model (one
``*_collection_links`` table per forge so the token column can be scoped to
the forge that owns it); same "eXist-db is the source of truth, asymmetric
push / one-shot initialize" invariant.

Out-of-scope clarifications worth recording now:

- **Not a transparent multi-backend**: a collection is linked to exactly one
  forge (GitHub **or** Codeberg), not mirrored to both. Multi-forge mirroring
  is a different feature with its own scoping concerns.
- **Self-hosted Forgejo / Gitea instances**: the Codeberg adapter should accept
  a configurable ``base_url`` so the same code serves ``codeberg.org`` and any
  institutionally-hosted Forgejo deployment (many EU universities now run
  their own). Treat this as a config field, not a separate plugin.
- **Auth**: Codeberg uses personal access tokens with a similar scope model to
  GitHub; encrypt at rest in the same way (extend ``SENSITIVE_KEYS``).

The trigger for the Codeberg variant is either (a) the GitHub integration
shipping and a user asking for the European equivalent, or (b) an
institutional deployment stating digital-sovereignty as a hard requirement
at onboarding.

*Added: 2026-04-16*
*Codeberg variant added: 2026-04-24*

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
- Publish / request revisions on submitted collections (simple state transition, one HTTP call)
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

## 15. Non-native plugin: GROBID — PDF → TEI import 🟡 Medium

Many editions begin from PDFs (prior printed editions, OCR-ed manuscript
transcriptions, scholarly articles cited as sources) and converting them
to TEI by hand is weeks of work. [GROBID](https://grobid.readthedocs.io/)
is an open-source Java service that extracts metadata, body text, and
bibliographic references from scholarly PDFs and emits valid TEI P5.
A non-native plugin wiring GROBID into the collection's upload flow
would give editors a "Import from PDF" starting point — imperfect but
weeks better than nothing.

### Motivation and use cases

- **Primary source digitisation**: a PDF of a 19th-century critical
  edition becomes a pre-populated TEI document the editor can then
  refine manually in the CodeMirror editor.
- **Reference mining**: drop a scholarly PDF of an article and let
  `/api/processReferences` return its `<listBibl>`, importable into
  the collection's bibliography (alternative path to the Zotero and
  CrossRef plugins).
- **OCR round-trip**: text from an OCR pipeline, wrapped in minimal
  PDF, becomes a skeleton TEI with approximate structure — faster
  than typing the `<div>` / `<p>` / `<pb>` skeleton by hand.

### Plugin shape

Non-native, same scaffolding as `zenodo_deposit`, `internet_archive`,
and `zotero_import`. Directory:

```
backend/app/plugins/grobid_import/
├── __init__.py
├── plugin.py        # Plugin class (no hook — manual-pull)
├── service.py       # httpx multipart POST to GROBID
├── config.py        # runtime config loader
├── schemas.py       # Pydantic
├── importer.py      # orchestration: upload → TEI → new document in eXist-db
├── router.py        # admin config + per-collection import endpoint
└── tests/
    ├── conftest.py
    ├── test_service.py
    └── test_importer.py
```

### External API

GROBID exposes:

| Endpoint | Purpose | MVP? |
|----------|---------|------|
| `POST /api/processFulltextDocument` | metadata + body + biblio → TEI | ✅ primary |
| `POST /api/processHeaderDocument` | metadata only | ➖ nice-to-have |
| `POST /api/processReferences` | biblio only → `<listBibl>` | ➖ biblio-only route |
| `POST /api/processCitationList` | parse a text list of refs | ✖ out of scope |

Multipart form with the PDF as `input` field; response is
`application/xml` (TEI). No auth, no API key — GROBID is unauthenticated
by default; operators rate-limit / restrict access at the network layer.

### Settings (hypothetical Alembic migration)

| Key | Type | Notes |
|-----|------|-------|
| `grobid_endpoint` | string | Base URL, e.g. `https://grobid.example.org` |
| `grobid_timeout_seconds` | int | Default 120 — GROBID is slow on multi-page PDFs |
| `grobid_max_pdf_size_mb` | int | Default 50; guards both Aracne2 and GROBID |
| `grobid_consolidate_citations` | bool | Passthrough for the GROBID ``consolidateCitations`` query param (0/1) |

No credentials. Nothing to add to `SENSITIVE_KEYS`.

### Flow

1. Admin stands up a GROBID instance (standard Docker image
   `lfoppiano/grobid:latest`, ~2 GB), reachable from the backend. Config
   panel in `/admin/plugins/grobid_import/config` lets Admin paste the
   endpoint URL.
2. Editor (EiC+) opens a collection, clicks "Import from PDF", picks a
   file. The plugin POSTs the PDF multipart-encoded to
   `POST {endpoint}/api/processFulltextDocument`.
3. On success (`200 application/xml`), the plugin validates the
   response is well-formed TEI (defusedxml parse), assigns a filename
   (`{original_basename}.xml`, collision-aware), and writes it to
   eXist-db under the collection's slug via the existing document
   upload service (same code path as a manual upload).
4. Editor is redirected to the new document in the TEI editor where
   they can refine the skeleton GROBID produced.

### Scope caveats

- **OCR quality drives output quality**: a PDF without proper text
  layer (pure image scans) yields essentially empty TEI. The plugin
  should detect and surface this case ("the PDF appears to be
  image-only; GROBID cannot extract text without OCR"). Detection is
  cheap — zero `<p>` children or empty `<text>` body.
- **Size limit + timeout**: GROBID scales poorly with page count; cap
  uploads at ~50 MB and bump the HTTP timeout to at least 120 s.
- **Filename collisions**: if a `{basename}.xml` already exists in the
  collection, append a numeric suffix — no overwrite without an
  explicit "replace" affordance.
- **Bibliography-only mode**: the second variant that only calls
  `/api/processReferences` and appends a `<listBibl>` to an existing
  `CollectionBibliography` is a natural follow-up; sits happily next
  to the Zotero + CrossRef import paths.

### Open questions

- **Hosting GROBID**: every deployment needs its own GROBID instance
  (there is no universally-accessible free SaaS). Document the Docker
  Compose snippet in `docs/OPERATIONS.md` when the plugin ships;
  without a reachable endpoint the plugin is dead weight.
- **Response streaming vs buffered**: GROBID responses for large PDFs
  can be 10 MB+ of TEI. Streaming into eXist-db rather than buffering
  in memory would help — but adds async complexity. Defer to buffered
  for MVP, revisit if it bites.
- **Variant for biblio-only route**: first iteration only wires
  `/processFulltextDocument`; `/processReferences` is a second
  iteration if editors ask. Bundling both from day one risks UI
  bloat on a feature that hasn't yet proved itself.
- **Security**: the plugin must forward the PDF to GROBID, so
  operators run a GROBID instance that trusts Aracne2. If the GROBID
  instance is shared across projects, firewall rules or a dedicated
  instance per deployment are advisable.

### Effort

~1.5–2 days once an operator has a reachable GROBID instance. The
plugin itself is glue: the hard part is standing up GROBID in the
deployment stack, which the plugin itself cannot automate.

### Prerequisites

| Prerequisite | Status |
|---|---|
| Non-native plugin scaffolding (Zenodo/IA/Zotero pattern) | ✅ |
| `PluginDataService` for per-collection state (if we want to track imports) | ✅ |
| eXist-db document upload service | ✅ (existing, used by all document-upload paths) |
| Reachable GROBID instance in the deployment | ❌ per-deployment |

### Trigger

Consider this when:

- A deployment explicitly needs to import non-trivial volumes of PDFs
  (edition digitisation campaign, OCR corpus intake);
- An operator has the infrastructure to run a GROBID instance next to
  the backend (roughly 4 GB RAM, a few GB of disk);
- The editors have understood the "GROBID is a skeleton, you still
  refine manually" expectation — otherwise the UX will feel broken
  on first contact with a poor-quality PDF.

Until then, manual TEI authoring plus the CrossRef / Zotero import
paths cover the bibliography-mining subset of what GROBID would do,
and full-body extraction from PDF is a niche that Aracne2 does not
need to solve in-platform.

*Added: 2026-04-23*

---

## 15. Non-native plugin: Matomo / Plausible analytics injector 🔵 To discuss

Inject a third-party analytics script (Matomo self-hosted or Plausible cloud)
on public pages so operators can answer "who is reading this edition?"
without relying on Aracne2's first-party counters alone.

**Motivation**

Some institutions need detailed traffic analytics — geographic spread,
referrer, time-on-page, funnel analysis — that the lightweight
first-party counter proposed in §4 cannot provide. Matomo and Plausible
are the two privacy-respecting options most commonly adopted in
academic and cultural-heritage deployments.

**Relation to §4 (Public reader statistics and analytics)**

§4 is about *first-party* aggregate counters computed from the
backend's access path. This entry is about *third-party* client-side
tracking. They are complementary, not alternatives:

- §4 is always on, privacy-by-default, and owned by Aracne2.
- §15 would be opt-in at install time, configured per-deployment,
  and the data would live on the operator's Matomo / Plausible
  instance.

**Scope (rough)**

- Admin activates the plugin and chooses provider (Matomo / Plausible)
  plus instance URL + site id.
- Plugin renders a `<script>` injection point on:
  - the public homepage and all public collection/document/bibliography
    pages,
  - each Websites module output (opt-in per-website, since a single
    Aracne2 deployment may host heterogeneous sites with different
    trackers).
- Respects a cookie-consent banner state (opt-in default for EU
  deployments).

**Why this is parked**

Three decisions must be made before writing code — each requires an
operator to take a position:

1. **GDPR stance** — consent banner required or opt-in tracking? The
   answer drives UI (a visible banner + preference persistence) and
   backend (consent state API).
2. **Default provider recommendation** — self-hosted Matomo (full
   control, heavier to operate) vs Plausible cloud (turn-key,
   ~$9/month). A deployment guide should push one over the other,
   not leave it fifty-fifty.
3. **Injection granularity** — platform-wide single tracker vs
   per-website trackers. If different Websites module outputs belong
   to different institutions, each may need its own tracker.

**Prerequisites**

- Cookie consent subsystem (currently absent from the platform).
- A clear product call on "track-by-default vs opt-in by default" —
  strongly affects UX of every public page.

**Trigger**

Build this once:

- An operator explicitly asks for one of the two providers, with
  their preferred compliance posture documented;
- A cookie-consent story exists in the platform (or is green-lit as
  part of the same effort).

Until then, §4 covers the basic "how many reads per document" need
without introducing third-party tracking at all.

*Added: 2026-04-23*

---

## 16. Non-native plugin: DataCite DOI minting 🔵 To discuss

Mint persistent DOIs for published collections and built websites via
an institutional DataCite allocator. Operationally a sibling of the
Zenodo Deposit plugin but architecturally heavier because of what
DataCite guarantees to the scholarly community.

**Why this is attractive**

Most institutional customers in the target audience already have a
DataCite allocator (university library, CNR, ministry). For them a
Zenodo deposit is redundant; what they want is a DOI in *their own*
prefix pointing back at their Aracne2-hosted edition. The plugin
would close that last gap on the "make editions citable" story.

**What makes it hard — and why we're not building it yet**

1. **Scarcity and cost of DOIs.** DataCite allocators charge per-DOI
   or per-year-quota. Unlike Zenodo where every deposit costs
   nothing, DataCite consumes budget. The UX cannot "mint on publish"
   naively — an operator mistake burns money. The plugin needs:
   - An explicit "mint" action, not an automatic hook;
   - Visible DOI-quota awareness in the admin UI;
   - An audit trail of who minted what and when.

2. **Pre-allocation workflow.** Real-world DataCite practice is to
   reserve a DOI in *draft* state well before publication (so the
   landing page, the PDF metadata, and the DOI itself can be prepared
   in parallel), and only *findable*-flip it at publication. The
   plugin has to model at least two DOI states (draft / findable)
   and let an editor move between them without losing the DOI.

3. **Immutability contract vs. unpublish-to-edit workflow.** This is
   the load-bearing question. DataCite's social contract is: "once a
   DOI is findable, the URL it resolves to is preserved forever, and
   the content at that URL should be preserved or explicitly
   superseded." Aracne2's current workflow lets an EditorInChief
   *unpublish* a collection, edit it, and re-publish — with no
   versioning on the public URL. If a DOI had already been minted,
   either:
   - The DOI keeps resolving to the same URL while the content
     changes silently underneath → **breaks the scholarly contract**,
     even if DataCite technically allows it.
   - The DOI is retracted / marked as withdrawn → **burns a DOI**
     for every "oops, one more document".
   - A new DOI is minted for the re-published version and linked to
     the old one via `related_identifiers` (`IsNewVersionOf` /
     `IsPreviousVersionOf`) → **correct, but doubles the DOI spend
     on every edit cycle and requires a versioning UX we do not
     currently have**.

   None of these is right by default. Zenodo sidesteps the problem
   because it *is* the archive — it keeps every version as a separate
   record and gives each its own DOI. Aracne2 is not an archive; a
   public URL mutates in place.

**Prerequisites before scoping this plugin**

- **A DOI-minting lifecycle spec**: what does "unpublish" mean for a
  DOI-tagged collection? Forbid it? Force re-mint on re-publish?
  Treat every edit after publish as a minor revision under the same
  DOI?
- **A versioning model for the public URL**: even if we keep minting
  one DOI per collection, the URL it points at has to remain stable
  and the *content* has to be either preserved or clearly versioned.
  This is a bigger change than the DataCite plugin itself — it
  touches collection publishing, website builds, and the unpublish
  action.
- **Per-deployment allocator credentials** encrypted in
  `system_settings` (same Fernet pattern as Zenodo).
- **Quota awareness**: a DataCite allocator quota endpoint polled
  periodically so the admin sees "DOIs remaining this year" before
  minting.

**Scope when it ships**

- Mint explicit (button per collection / per website), never automatic.
- Draft / findable state machine with operator confirmation on
  findable-flip.
- `related_identifiers` emission matching the chosen versioning
  model (decided in the lifecycle spec above).
- Reuses the `DepositMetadata` intermediate factored out for Zenodo
  so the Pydantic model is shared; only the serialiser differs.
- DataCite test instance (`api.test.datacite.org`) selectable in the
  admin UI for smoke testing without consuming real DOIs.

**Trigger**

Build this once the institutional operator on the receiving end has:

- A clear position on unpublish semantics (preserve / version / forbid);
- A committed DataCite allocator budget and quota;
- Agreement to use the draft-first workflow rather than mint-on-publish.

Zenodo covers the "cite-this-edition" use case in the meantime,
which is the 80 % solution for non-institutional deployments.

*Added: 2026-04-23*

## 17. Non-native plugin: IIIF integration (+ Mirador / OpenSeadragon) 🔵 To discuss

Let Aracne2 consume — and optionally serve — IIIF (International Image
Interoperability Framework) resources, so editors can reference
high-resolution facsimiles already digitised by cultural institutions
without re-uploading, and so external aggregators can harvest Aracne2
content through the DH standard.

**Motivation**

The target audience — philologists, archivists, DH researchers —
routinely works with manuscripts that have already been digitised and
exposed via IIIF by institutions like the Vatican Library, BnF
Gallica, British Library, Library of Congress, or DH aggregators.
Today, Aracne2 editors either re-upload copies locally (wasteful,
legally grey) or link out with a plain URL. A IIIF integration would
let them reference the canonical manifest and render a zoomable,
tiled viewer inside the platform.

**Three possible scopes with very different costs**

| Scope | What Aracne2 does | Effort | Value |
|---|---|---|---|
| **A — Consumer** | Opens remote IIIF manifests in an embedded viewer on public reader + TEI editor. No local tile server. | ~1 week | 🟢 High |
| **B — Provider** | Exposes Aracne2's own uploaded images as IIIF Image API endpoints + per-collection IIIF Presentation API manifests. Requires a tile server (pyvips / Cantaloupe / Serverless IIIF). | ~3 weeks | 🟡 Medium — depends on how many aggregators the operator needs to reach |
| **C — Full** | A + B + round-trip between TEI `<zone>` and W3C Web Annotations so zones author-ed in Aracne2 surface in Mirador, and remote annotations import into the TEI zone editor. | ~6+ weeks | 🟡 Very high but far out |

MVP recommendation is **A**: it is the 70 % of the value at a fraction
of the cost, and it does not touch Aracne2 storage.

**Viewer choice is itself an open question**

"IIIF integration" does not automatically mean Mirador. Three
realistic options, each with a different footprint:

| Viewer | Bundle size | Stack | Strengths | Weaknesses |
|---|---|---|---|---|
| **Mirador 4** | ~1.2 MB | React | Multi-window workbench, manuscript comparison, annotation editor, DH de-facto standard | Heavy; React-in-Vue requires iframe or isolated mount |
| **Clover IIIF** | ~400 KB | React | Modern UI, better DX, audio/video support | Smaller community, less mature |
| **OpenSeadragon + IIIF plugin** | ~150 KB | Vanilla JS | Drops into Vue natively, deep zoom, simple API | Viewer only — no comparison, no annotation editor, consumes IIIF Image API but not full Presentation manifest |

For the single-manuscript-at-a-time workflow that dominates Aracne2
usage, **OpenSeadragon** is likely sufficient. Mirador pays off
only when the audience needs the multi-window comparison
workbench — which is a real but niche use-case.

**Co-existence with the current facsimile system**

Aracne2 already has a mature facsimile pipeline: `<pb facs="#fN">`,
`<surface>`/`<zone>` editor, the one-to-one viewer mode. The IIIF
plugin must **not** replace it. Design it as a parallel channel:

- If a document has a `iiif_manifest_url` (new optional field), the
  public reader renders the configured IIIF viewer on the manifest.
- Otherwise the existing surface/zone flow stays unchanged.
- If both are present, either the editor picks the active one per
  document, or the plugin config chooses a global default.

**Open questions that must be resolved before scoping code**

1. **Scope A vs B vs C** — confirm we start with A only. B and C are
   cost-multipliers that can be added later if a concrete demand
   appears.
2. **Viewer choice** — Mirador (heavy, full toolkit) vs OpenSeadragon
   (light, viewer-only) vs Clover (middle ground). Each has
   downstream implications for bundle size, annotation support, and
   how close the Vue frontend feels to the rest of Aracne2. The
   answer depends on whether the target audience actually uses
   Mirador's workbench features or just wants "zoomable pages next
   to transcription".
3. **Where does the manifest URL live?** Three options, each
   reasonable:
   - **a) In the TEI** — e.g. `<graphic url="…iiif-manifest.json"/>`
     recognised by the editor. Cleanest, data lives inside the
     document.
   - **b) As an Aracne2 field on `document`** — extra column or a
     `plugin_data` row. Easier to edit in the UI, but outside the
     TEI, so harder to round-trip to external tools.
   - **c) Collection-level default + per-document override** — the
     most flexible but the most UI to build.
4. **Annotations** — for the MVP the plugin can display annotations
   already present in a remote manifest but does **not** author new
   ones (no TEI zone ⇄ W3C Web Annotations mapping). Confirm this
   scope cut is acceptable. Doing annotations round-trip properly is
   the hard part of scope C.
5. **Access control** — are the referenced IIIF manifests always
   public, or do we need to support the IIIF Auth API (institutional
   collections with subscription or login gates)? Auth support is
   non-trivial and should be out of MVP.

**Prerequisites**

- **Decisions on the five open questions above.**
- If scope B is ever scoped: a tile server story (pyvips-in-FastAPI
  vs sidecar Cantaloupe vs pre-generated tiles) — all non-trivial
  operationally.
- If scope C is ever scoped: a concrete mapping spec between TEI
  `<zone>` + `<pb facs>` and W3C Web Annotations. The data models
  differ; round-tripping losslessly is not free.

**Trigger**

Build scope A once:

- The five open questions have concrete answers;
- A concrete first project / deployment actually references a IIIF
  manifest that would be re-hosted locally today;
- The viewer trade-off has been tested on a sample manifest to
  confirm the chosen viewer handles the real-world bundle size /
  UX expectation.

Until then, the existing facsimile pipeline covers the in-platform
"page image next to transcription" case, and external links to the
owning institution's viewer cover the referenced-manuscript case.

*Added: 2026-04-23*

---

## 18. S3-compatible media backend (read + write, private buckets) 🟡 Medium

Swap Aracne2's filesystem-backed media storage (`documents_media_root`)
for a pluggable `StorageBackend` with an S3-compatible implementation
alongside the current local one. Deployment chooses at install time;
buckets are **private**, reads use server-generated signed URLs.

**Motivation**

Facsimile-heavy projects (manuscripts, archives, codex imaging) push
media volumes into tens or hundreds of gigabytes per collection. Local
disk scales poorly in that range:

- **Operational cost** — single-volume filesystem vs cheap object
  storage (R2 / B2 / MinIO self-hosted) tips hard towards cloud
  beyond ~50 GB.
- **Backup** — the current backup plugin zips the local tree, which
  becomes unworkable at scale; S3-level snapshots are a solved
  problem.
- **Durability** — a local disk is a single point of failure; S3
  providers quote 11 nines durability.
- **Horizontal scale** — with local storage every backend container
  needs either shared storage or pinned affinity. S3 removes that
  constraint.
- **Jurisdictional compliance** — some institutions are required to
  keep assets in-region; S3-compatible providers exist in every
  jurisdiction (AWS regions, Cloudflare regions, SURF for NL/EU,
  MinIO on-prem for "never leaves the building").

A previous discussion explored a simpler model (public bucket with
URL references, no upload through Aracne2 — see the "Remote images
base URL" proposal archived on 2026-04-23) and rejected it because:

- Public buckets leak draft-stage facsimiles;
- GDrive / Dropbox / pCloud do not fit the `{base_url}/{filename}`
  pattern and fragmenting support per provider is not worth it;
- Aracne2 lost the ability to list / verify images, degrading the
  editor UX;
- Website ZIP downloads and backups stopped being self-contained.

The right direction is a proper **private S3 backend with signed
reads** that keeps Aracne2 in control of the upload/read lifecycle.

**Scope**

Backend:
- Introduce a `StorageBackend` ABC with three methods: `put(path,
  content) -> None`, `open(path) -> AsyncIterator[bytes]`,
  `url_for(path, *, public: bool = False) -> str`. Plus `delete`,
  `exists`, `list_prefix`.
- Implementations: `LocalFilesystemBackend` (current behaviour,
  URLs point at the FastAPI media router) and `S3Backend` (uses
  `aioboto3` or `aiobotocore`, generates pre-signed URLs for reads).
- Single global backend selected by env var, not per-collection —
  simpler ops, and institutions rarely mix.
- Private bucket by default. Signed URLs with a configurable TTL
  (default: 15 minutes). Public-bucket mode as an opt-in for
  deployments that want direct CDN serving.
- All existing paths that touch `documents_media_root` route through
  the backend interface — the `documents`, `websites` (build-time
  media copy), and `backup` plugins each need targeted changes.

Frontend:
- Upload flow stays visually identical — the backend handles the
  dispatch.
- Rendered pages use signed URLs transparently. Signed URL refresh
  strategy: re-mint on each page render (accept some latency
  overhead) or cache per session (more complex).

Admin:
- One-shot migration tool: "move local media to S3 and update
  references". Opt-in, idempotent, dry-run mode.
- Config panel showing backend health (can the process reach the
  bucket? is the signer configured?).

**Open questions**

1. **Async client choice** — `aioboto3` (maintained, follows
   boto3's API shape) vs `aiobotocore` (lower-level, lighter, but
   less ergonomic). Either works with AWS / R2 / B2 / MinIO / SURF
   because all speak the S3 protocol.
2. **Signed URL TTL and caching** — 15 min default is conservative
   but forces re-minting on long-lived editor sessions. Longer TTL
   (1 h, 24 h) simplifies UX but increases blast radius if a URL
   leaks. Probably configurable with a safe default.
3. **Website ZIP downloads** — currently self-contained. With S3
   reads, the build step either (a) downloads all referenced
   objects into the ZIP (restoring self-containedness, doubling
   bandwidth on build), or (b) writes URLs into the ZIP and the
   downloaded site depends on the bucket staying up. Decision
   needed — probably (a) as default with an opt-out.
4. **Backup plugin changes** — stop zipping `documents_media_root`;
   instead, document the expectation that S3-level snapshots /
   versioning are the backup. Or keep an optional "include media in
   backup ZIP" for admins who still want a single archive.
5. **Failure mode when S3 is unreachable** — current upload returns
   immediately after `write()`. An S3 PUT that times out should not
   eat the editor's file without feedback. Retries + clear error
   surfacing are part of scope.
6. **Bucket layout** — mirror the current `{collection_slug}/
   {doc_filename}/{image_file}` tree verbatim, or flatten with a
   content-hash scheme? Mirroring is easier to debug by hand; hashes
   are immutable. Probably mirror for familiarity.
7. **Multi-tenant** — if a single Aracne2 deployment eventually
   hosts multiple institutions (not today's model), they likely
   want separate buckets. Parking this sub-question — one backend
   config is enough for the one-institution deployment model.

**Prerequisites**

- A real deployment that has outgrown local disk (or is about to).
  Until then, local storage is simpler, cheaper for small corpora,
  and less coupled to cloud provider trust.
- A concrete decision on signed URL TTL policy (see §2 above).
- Budget for re-visiting the backup plugin and the website ZIP
  generator — both depend on "media lives on the filesystem next
  to the backend" assumption.

**Trigger**

Build this when any of these happens:

- A deployment reports filesystem pressure (> 100 GB, slow
  backups, disk-full outages);
- An institution explicitly asks for S3 / R2 / SURF to keep data in
  their controlled infrastructure;
- Horizontal scaling is needed (multiple backend containers behind
  a load balancer) — local disk becomes a hard blocker.

The refactor is additive: `LocalFilesystemBackend` remains the
default and the existing deployments keep working unchanged.

*Added: 2026-04-23*

---

## 19. CI pipeline on GitHub Actions 🟡 Medium

Add a `.github/workflows/ci.yml` that runs lint + tests + dependency
scans on every push and pull request. Today every pre-merge check is
manual: `pytest` locally, the periodic maintainer-triggered
`Security_review_YYYY-MM-DD.md` audits for `pip-audit` / `npm audit`,
code review by eye for formatting drift.

**Motivation**

The manual flow works at the current pace (small team, one or two
PRs a week, disciplined maintainer). It stops scaling when any of
these changes:

- PR throughput increases (catching a formatting issue in code review
  becomes time a reviewer doesn't have);
- New contributors join (onboarding "run these seven commands locally
  before committing" is brittle);
- A CVE lands between two scheduled security reviews (today the
  window is ~monthly; CI closes it to "next PR merge");
- Coverage gates start mattering for regression insurance.

**Shape**

Four jobs running in parallel per trigger:

1. **backend-lint** — `ruff check`, `ruff format --check`, `mypy app`.
   ~1 minute.
2. **backend-test** — `pytest app/tests app/plugins --cov=app
   --cov-fail-under=70`. Uses GitHub Actions `services:` sidecars to
   spin up Postgres 15 + eXist-db 6.2 alongside the runner. ~3-4
   minutes.
3. **security-scan** — `pip-audit -r backend/requirements.txt`,
   `npm audit --audit-level=high` in `frontend/`. ~1 minute.
4. **frontend-typecheck** — `npx vue-tsc --noEmit`, `npm run lint`,
   `npm run test`. ~2 minutes.

Total wall-clock on a PR: ~4 minutes (jobs run concurrently).

**What it intercepts** (and what it doesn't)

Blocks PRs for: CVE in a pinned dependency, broken pytest, mypy type
error, TypeScript type error, ruff formatting drift. Does **not**
block for: bugs not covered by a test, performance regressions,
UX regressions, accidental exposure of secrets beyond a `.env` leak.
CI is the first net, not the only one.

**Open questions**

1. **Branch protection policy** — the workflow is informative unless
   `main` is gated. Options: none (status check advisory), required
   checks before merge, required + at least one approval. Decide
   based on whether direct push to `main` is still acceptable.
2. **Test environment parity** — the current tests run under SQLite
   in-memory, not PostgreSQL. CI could bring up Postgres but the
   tests would need to accept a real DB and run migrations. Scope
   decision: run the existing SQLite-based suite (matches today) vs
   upgrade tests to Postgres in CI (closer to prod, more setup
   work).
3. **Dependency scanner severity threshold** — `--audit-level=high`
   lets moderate-severity findings through for now. Strictness
   should match the maintainer's tolerance for false positives.
4. **Coverage gate number** — the suite currently has generous
   coverage; a 70 % floor is safe. Ratcheting up over time (80 %,
   90 %) is the usual pattern, but requires more frontend tests
   first.
5. **Docker image build in CI** — not strictly CI, but often bundled.
   Only worth it if the repo starts publishing images to a registry
   (Docker Hub, GHCR). Defer until then.

**Prerequisites**

- A concrete position on branch protection (see §1 above).
- Env var plumbing: `config.py` reads ~15 required vars; CI needs a
  `ci.env` sample or inline `env:` block. For this repo nothing
  listed there is a real secret — they are all dev placeholders —
  so a committed sample is fine.

**Trigger**

Build this once:

- A second regular contributor is onboarding and the "run X commands
  locally" friction is real, or
- A CVE lands between scheduled reviews and nobody noticed until a
  security review caught it after-the-fact, or
- Branch protection on `main` becomes a governance requirement (e.g.
  for an institutional deployment that audits the repo).

Until then, the manual `Security_review_YYYY-MM-DD.md` cadence —
triggered locally via Claude on the maintainer's cadence — produces
a durable paper trail of exactly what was checked and when, which is
a credential a green ✅ badge does not replicate.

*Added: 2026-04-23*

---

## 20. Admin view for the global audit log 🟡 Medium

The `audit_log` PostgreSQL table is already populated by the platform —
auth events (login / refresh / password change), XML DB writes
(`collection.created`, `document.uploaded`, `collection.published`, …),
plugin activations, settings changes, and more. The data is consulted
indirectly today (per-collection workflow history under
[xmldb.py:345](backend/app/services/xmldb.py#L345-L360)) but there is
no global admin surface — querying across actors, actions or time
ranges requires opening psql.

A `/admin/audit-log` view would close that gap.

**Motivation**

- **Compliance / accountability**: an institutional deployment auditing
  who modified which collection at which time needs a queryable record;
  pointing them at a SQL prompt is not a credible answer.
- **Incident triage**: when a published collection appears to have lost
  data or a user reports a permission anomaly, the audit trail is the
  fastest path to "who did what just before the bug surfaced". Today
  the maintainer has to open a shell on the prod DB.
- **Editorial transparency**: EditorInChiefs already get a per-
  collection workflow history; an admin-level cross-collection view is
  the natural complement.
- **Retention policy verification**: the `audit_log_retention_days`
  setting (default 90) is already enforced by the seed/cleanup logic,
  but there is no way to *see* the rows about to be pruned. A view
  also makes the policy concrete to admins.

**Scope**

Backend:
- `GET /api/v1/audit-log` — Admin-only, paginated.
  Query params: `actor_id`, `actor_username` (substring match),
  `action` (exact or `LIKE`), `target_type`, `target_id`,
  `from`/`to` (ISO 8601 timestamps), `page`, `per_page`.
  Returns a `PaginatedResponse[AuditLogEntry]` with the standard
  envelope. ACL: `Depends(require_role("Admin"))`.
- `GET /api/v1/audit-log/actions` — distinct action names for the
  filter dropdown (cached, invalidated on insert).
- `GET /api/v1/audit-log/{id}` — single row including the full JSONB
  `payload`. Separate endpoint to keep the list response lean.
- `GET /api/v1/audit-log/export.csv` — same filters as the list,
  streams a CSV with the canonical columns. No pagination — the
  filter is the only knob that bounds the size.

Frontend:
- `/admin/audit-log` view (Admin-gated).
- A toolbar with the filters above; results in a paginated table —
  columns: `occurred_at`, `actor_username`, `action`,
  `target_type`/`target_label`, `ip_address` (already hashed in
  prod by the existing logger middleware).
- Row click opens a side panel with the JSONB `payload` rendered as
  pretty JSON and the user-agent string.
- Sidebar link under the **Amministra** section, next to Plugin and
  Webhook (Admin role).

Privacy:
- `ip_address` is already a hash in production (SHA-256 with the
  `JWT_SECRET` salt — see CLAUDE.md). The view shows the hash, never
  a reverse lookup.
- `payload` may contain references to internal IDs but never full
  document bodies (the audit logger has always stored metadata only,
  see [services/xmldb.py:199](backend/app/services/xmldb.py#L199)).

**Open questions**

- **Performance on large tables**. With 90-day retention and a busy
  multi-editor deployment the table can reach low-millions of rows.
  Need an index on `(occurred_at DESC)` and a composite on
  `(actor_id, occurred_at DESC)` for the actor-filter case.
  Alembic migration when the view ships.
- **Full-text search on `target_label` and `payload`**. Optional, but
  often the only useful filter ("when was this specific doc renamed?").
  Would justify a `tsvector` GIN index.
- **JSONB rendering**. Some payloads are flat (`{"old": "...", "new":
  "..."}`), some nest deeply. Render as `<pre>` with syntax
  highlighting via the existing `vue-i18n` consumer pattern, or
  fall back to a tree widget?
- **Action vocabulary**. Today action strings are free-form (e.g.
  `collection.created`, `auth.login`, `plugin.activated`). Worth
  cataloguing the canonical set so the filter dropdown is curated
  instead of "every distinct value ever inserted".
- **Free-text vs structured filtering**. A single search input that
  matches against `actor_username`, `action`, `target_label` is
  often what an admin actually wants — propose alongside the
  structured filters and remove whichever turns out to be unused.
- **Export format**. CSV is enough for spreadsheets; some institutional
  audits ask for a signed JSON Lines export. Defer the signed variant
  unless explicitly requested.
- **Real-time tail mode**. A "live" toggle that polls every N seconds
  and prepends new rows would be useful during an incident. Easy
  add-on, gate behind an explicit toggle so the default page is
  static.

**Prerequisites**

- `audit_log` table — already in place.
- `AuditLog` ORM model — already in place
  ([backend/app/models/audit_log.py](backend/app/models/audit_log.py)).
- `audit_log_retention_days` setting — already seeded in
  [db/seed.py:42](backend/app/db/seed.py#L42).
- IP hashing in production logging — already in place (CLAUDE.md
  §Security).
- `PaginatedResponse` envelope — already used for collections / users.
- Admin-gated route + sidebar pattern — already used by Plugin /
  Webhook / Backup.

**What this is not**

- Not a replacement for application-level logs (structlog / Docker
  logs). Those record HTTP traffic + diagnostics; the audit log
  records *intentional, user-attributable* actions only.
- Not a "history of every field change". The audit log captures
  domain events, not row-level diffs. Per-collection workflow history
  already covers the editorial side.

**Trigger for implementation**

- A first non-maintainer admin asks "who deleted X" and the answer
  requires shell access, or
- A deployment hits a compliance review that explicitly names "audit
  trail accessible to admins" as a control.

Until then, the per-collection workflow history covers ~80% of what
editors actually ask for, and `psql` covers the rest for the
maintainer.

*Added: 2026-04-27*

---

*Last updated: 2026-04-27*
