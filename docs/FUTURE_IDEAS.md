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

## 1. ~~CLI import/export tool~~ ✅ Shipped

Shipped in Milestone 1 (Phases CLI-A, CLI-B, CLI-C). The tool lives in
[`cli/`](../cli/) of the monorepo, installable via `pip install -e cli/`
from a fresh checkout (no PyPI publish — invite-only audience).

**Auth subsystem (Phase CLI-A)**: new `personal_access_tokens` table
(Alembic 0075) — long-lived bearer tokens an Editor+ issues from
their own Profile to authenticate the CLI. Plaintext format
``aracne2_pat_`` + 32 url-safe random bytes; bcrypt-digest stored
in DB; the auth middleware in ``app/middleware/acl.py`` detects the
prefix and dispatches to ``resolve_pat`` *before* the JWT decode
path, so existing ``require_role`` guards keep working unchanged.
PAT inherits the issuer's currently-active role (no per-token
scoping in v1). Endpoints under ``/users/me/tokens`` (GET/POST/DELETE,
Editor+).

**Frontend (Phase CLI-B)**: a self-service "API tokens" card on
``ProfileView`` with an issue modal that flips to a "copy this once"
panel after creation, mirroring the MCP-token UX from the
admin/CorporaView surface.

**CLI tool (Phase CLI-C)**: a typer + httpx + rich app with four
commands and ``--profile NAME`` for multi-deployment users.

```
aracne login --host https://aracne.example.org   # paste PAT, GET /auth/me to verify
aracne whoami
aracne import --collection my-corpus --dir ./tei-files/ \
              --on-conflict skip|overwrite|fail   # default: skip
aracne export --collection my-corpus --output corpus.zip
aracne export --collection my-corpus --as-of 2026-04-01 --output q1.zip
```

The ``--as-of`` flag walks ``document_versions`` per filename,
picks the highest ``publication``-origin row whose
``created_at <= as-of``, and downloads that version's content —
this is what the Milestone 1 acceptance criterion ("recover the
previous content history") is satisfied by.

Out of scope for v1 (deferred to a future milestone if needed):
``aracne validate`` (offline schema check), ``aracne delete``
(destructive ops stay UI-only), full-history serialization,
PyPI publication, per-token scopes.

Original idea note kept below for historical context.

**Original motivation**
Large editorial projects often start with an existing corpus of TEI files on a
filesystem or in a zip archive. Manually uploading hundreds of documents through
the web UI is impractical. Similarly, full collection exports for archiving or
migration need to work headlessly.

**Original open questions** (resolved during implementation)
- API token table: shipped as new ``personal_access_tokens`` parallel to
  ``mcp_tokens``, per-user (not per-corpus).
- Conflict resolution on import: ``--on-conflict {skip,overwrite,fail}``;
  default ``skip`` for tolerance on re-imports of the same corpus.

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

## 20. ~~Admin view for the global audit log~~ ✅ Shipped

> Shipped 2026-05-03 as Milestone 2 item 1 of 3. See
> [Aracne_Roadmap.md](Aracne_Roadmap.md) for the implementation
> summary; the original design notes below are kept for reference.

🟡 Medium (historical priority)

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

## 21. MCP server — Phase 2 (write tools) 🟡 Medium

The MCP server shipped in Phase 1 is read-only by design (eight tools
+ four resource templates, all gated behind a per-corpus bearer
token). Phase 2 turns it into an active assistant: tools that
*produce* TEI and, in some cases, *mutate* the platform.

**Idea**

Add four write or write-adjacent tools, each individually toggleable
per corpus via a new `mcp_allow_writes` boolean column on
`mcp_tokens` (default false):

| Tool | Mutation? | Sketch |
|---|---|---|
| `crossref_to_tei(doi[])` | No — output only | Editor in chat: "import these 30 DOIs as bibliography". The tool returns ready-to-paste `<biblStruct>` TEI; the editor pastes them into the TEI editor manually. Reuses the existing `crossref_lookup` plugin's service layer. |
| `crossref_lookup(query)` | No | Search CrossRef by title / author. Returns candidates so the LLM can ask the editor to confirm before chaining into `crossref_to_tei`. |
| `zotero_import_to_collection(group_id, slug)` | Yes (DB write to `collection_bibliography`) | Import a Zotero group library as a bibliography in a corpus collection. Reuses the `zotero_import` plugin's importer. Real mutation — sits behind the per-corpus consent toggle and an optional second factor (admin re-confirm by email / Slack). |
| `start_collection_validation(slug)` | Trigger only — read-only effect | Kick the validation job that already exists as a REST endpoint. The result lands in `collection_validation_runs` and is queryable via existing tools. |

**Open questions**

- **Consent model**. Claude Desktop calls tools without asking the
  user (the LLM decides when to call them). For destructive writes
  that isn't enough — we want each `tools/call` on a write tool to
  log a proposal that an admin must approve out-of-band before the
  side effect lands. Sketch:
  - First call → write a `mcp_pending_action(token_id, tool, args,
    expires_at)` row, return `{"status": "pending", "approval_url":
    "https://aracne2.example/admin/mcp/pending/<id>"}`.
  - Admin clicks approve → the write goes through, the LLM sees the
    success on a follow-up `tools/call` keyed by the same id.
  - Open: does the consent UX make the tools too clunky to actually
    use? An alternative is per-corpus *blanket consent* — once the
    admin enables `mcp_allow_writes`, every write is allowed without
    second-factor. Blast radius is bounded by the corpus, so blanket
    consent is defensible if revocation is fast.
- **TEI insertion vs return-only**. `crossref_to_tei` is the safest
  shape (LLM produces text, editor pastes). `zotero_import_to_collection`
  cannot be made return-only — the bibliography must end up in the
  DB. Differentiate the two consent levels: "return TEI snippets"
  (default-on) vs "mutate DB" (default-off, per-corpus opt-in).
- **Outcome reporting**. After a successful write, the tool result
  needs to carry enough information for the LLM to confirm to the
  editor *what* happened — not just "OK" but "imported 27 of 30
  Zotero items, 3 skipped because of missing DOIs". The wire
  format is the standard MCP `content` envelope; the design choice
  is which fields to include without leaking IDs the editor doesn't
  control (e.g. internal UUIDs).
- **Audit log impact**. Every write tool emits an `audit_log` row
  attributed to the token's `created_by` user, not to the bearer
  context (which is anonymous to the platform). The token's row
  already records the issuer's user id, so this is a one-line
  patch — but worth calling out because it conflates "Admin issues
  the token" with "Editor uses the token", which can mislead an
  auditor reading the log later.

**Why deferred**

- Phase 1 has been live for less than a week (as of 2026-04-28); we
  don't yet know which of these tools editors actually want. Two of
  the four (Zotero, GROBID derivatives) duplicate plugins that
  already have UI surfaces — adding a chat-driven path is only
  worthwhile if those surfaces feel cumbersome in real use.
- The consent UX is the genuinely hard part. The simpler "blanket
  per-corpus consent" model is fine technically but skips the
  editor's chance to refuse a specific call. The proposal-pending
  flow needs UI work and probably an out-of-band notification (email
  / webhook) to the admin, which is feature-creep.

**Prerequisites**

- A new column `mcp_allow_writes BOOL DEFAULT FALSE` on `mcp_tokens`,
  flipped in the corpora admin panel.
- (Optional, for the consent flow) a new table
  `mcp_pending_actions(id, token_id, tool, args_json, expires_at,
  approved_at, executed_at)` plus an admin route to approve / reject.
- Audit attribution lookup (`token.created_by`) plumbed into every
  write tool's audit row.

**Trigger for implementation**

- An editor explicitly asks for chat-driven Zotero / CrossRef
  imports more than once, or
- The Phase-1 `last_used_at` analytics show heavy daily MCP use —
  signal that the editorial team has internalised the chat workflow
  and would benefit from removing the round-trip to the TEI editor.

*Added: 2026-04-28*

---

## 22. MCP server — Phase 3 (identity, members, audit) 🟡 Medium

Once Phase 1 is in heavy use across multiple editors and Phase 2 is
shipping writes, the next bottleneck is **identity**: today every
MCP request is anonymous from the platform's perspective (the bearer
token resolves to a corpus, not a user), and Admin manually
distributes per-corpus tokens. Phase 3 introduces a personal-token
model and an audit surface that scales beyond a handful of editors.

**Idea**

Three coordinated additions:

### a. Personal MCP tokens

An editor opens `/profile/mcp-tokens`, generates a token tied to
their own user. The token's effective scope is the *union* of every
corpus the editor is a member of (see point b). Replaces or
complements per-corpus tokens.

- Pro: removes the Admin-distributes-tokens bottleneck. Editor
  rotates their own token any time without touching the Admin.
- Pro: every MCP request now has a real user attached, which solves
  Phase 2's audit-attribution problem properly.
- Con: needs `corpus_members` (b) to be useful — a personal token
  with no membership can't access anything.

### b. `corpus_members` table

The schema introduced in Phase 1 already anticipated this — see
the docstring of `app/models/corpus.py`. Two columns: `corpus_id`,
`user_id`. UI in the corpora admin panel ("Add member" pulldown
with the existing user list).

Membership is the source of truth for *both* personal MCP tokens
(point a) and a future feature where the TEI editor's AI panel can
filter to "the corpus I'm working on" — closing the gap that Phase 1
intentionally left open for the in-itinere case.

### c. Per-token audit log

A new `mcp_audit_log(timestamp, token_id, user_id, tool_name,
args_hash, result_size_bytes)` table, written by the JSON-RPC
dispatcher on every `tools/call`. Visualised in the corpora admin
panel as "Last 100 calls" per token, and exposed as a filterable
view (`/admin/mcp/audit`) for instance-wide monitoring.

Cardinality is much higher than `audit_log` — a single editor can
trip 60 calls/minute — so it warrants its own table with a TTL
(`mcp_audit_retention_days`, default 30) so it doesn't grow
unbounded.

### d. Per-corpus rate limit override

`mcp_rate_limit_per_minute` column on `corpora`, default null = use
the global 60/min. An admin can dial up a "Demo public" corpus to
600/min and dial down a sandbox corpus to 5/min. Trivial backend
change — slowapi already supports per-key limits.

**Open questions**

- **Personal-token membership UX**. When an editor generates a
  personal token, should they see *which* corpora it covers? A
  "scope preview" list at generation time would be honest but
  intricate UI. The simpler answer: just say "this token grants
  access to every corpus you are currently a member of" and let the
  editor check `/admin/corpora/membership` separately. The simpler
  UX wins.
- **Personal vs corpus tokens — coexistence or replacement?** If
  both exist, an admin can issue per-corpus *and* an editor can
  have personal tokens. That's nice for flexibility but doubles
  the surface to maintain. Cleaner: deprecate per-corpus tokens
  once personal tokens land, and migrate existing per-corpus
  tokens by re-issuing personal ones. Decision belongs to the
  implementation turn.
- **AI panel scope filter (in-itinere)**. The TEI editor's AI panel
  today operates on a single document at a time. Once `corpus_members`
  exists, we can offer "ask the AI about my whole corpus" with
  RAG over only the editor's corpora. Big feature on its own;
  worth a separate FUTURE_IDEAS entry when its time comes.

**Why deferred**

- Personal tokens are a UX win, not a security win — the per-corpus
  model already satisfies the security model (corpus-scoped, fully
  revocable). The trigger to add personal tokens is operational
  pain ("Admin spends 30 minutes every Friday issuing tokens"), not
  a fundamental gap. As of 2026-04-28 we have zero editors actually
  using MCP; defer until that pain materialises.
- Audit log is the *right* feature for compliance reviews and large
  multi-tenant deployments. For the closed-editorial audience it is
  overkill — the corpora admin panel already shows `last_used_at`,
  which answers ~80% of "is this token active?" questions without
  a dedicated audit table.

**Prerequisites**

- `mcp_tokens.user_id` foreign key (nullable for legacy per-corpus
  tokens).
- New table `corpus_members(corpus_id, user_id)`.
- New table `mcp_audit_log(...)` + retention sweeper job (the same
  `apscheduler` already used for session expiry / audit log retention).
- New endpoint `/profile/mcp-tokens` for editor self-service.
- Frontend: a thin token-management surface at `/profile/mcp-tokens`
  + a filterable audit view at `/admin/mcp/audit`.

**Trigger for implementation**

- The deployment grows past ~5 active MCP editors and Admin
  reports "issuing tokens has become a chore", or
- A compliance review explicitly requires per-user attribution in
  audit logs, or
- The first deployment hosts multiple research groups in the same
  Aracne2 instance and groups want self-service token management.

*Added: 2026-04-28*

---

## 23. End-to-end HTR pipeline — large-corpus image-to-zone import 🟡 Medium

The platform today exposes a thin HTTP surface for HTR-driven zone
creation: `POST /api/v1/collections/{slug}/documents/{filename}/facsimile/{surface_id}/zones/import`
([backend/app/routers/zones.py:91](../backend/app/routers/zones.py#L91))
accepts a JSON list of zones with semantics identical to PUT — i.e.
the same payload shape the manual editor saves. Anything beyond that
(parsing standard HTR formats, ingesting thousands of images at
once, letting an editor accept / correct / reject machine output)
is on the roadmap, not in the current build.

This entry sketches the full design so the next contributor (or
future self) can pick it up without re-deriving the pieces.

### Idea

A "Documents → Import HTR output" surface in the collection detail
view that walks an editor through:

1. **Batch image upload** — drop *N* images on the page; backend
   stores them under `media_dir/<slug>/<doc>/...` and produces
   `<surface>` skeletons in the TEI document.
2. **HTR format ingestion** — for each image (or for the whole
   batch as a ZIP), accept ALTO XML or PAGE XML produced by an
   external HTR engine. Parse it server-side into the platform's
   internal zone shape.
3. **Review queue UI** — show the candidate zones overlaid on the
   image with their text and confidence score. Per-zone actions:
   *accept* (zone lands in `<zone>`), *correct* (edit coords or
   text inline), *reject* (drop). Bulk actions: accept-above-N%,
   reject-below-N%.
4. **Commit to TEI** — once the editor closes the queue, the
   accepted zones write to the document's `<facsimile>` section
   with `xml:id` slugs, and the OCR'd text becomes `<line>` /
   `<lb>` elements with `facs="#zone-id"` cross-pointers.
5. **Word-level alignment (optional)** — when ALTO carries
   per-word coordinates, surface them as `<w facs="#word-id">`
   in the transcription. The current README already advertises
   word-level alignment as future work.

### Open questions

- **Where does the HTR engine actually run?** Three plausible
  positions:
  - *Outside Aracne2* — the editor produces ALTO / PAGE elsewhere
    (Transkribus desktop, eScriptorium on a GPU cluster) and
    uploads it. **Recommended starting point** — zero infra burden
    on Aracne2, decouples release cadences, supports "I already
    have a workflow" deployments.
  - *Bundled non-native plugin* — a `htr_engine` plugin that wraps
    a containerised Kraken or eScriptorium API. Lets a deployment
    bring HTR in-house. Needs a GPU on the host, careful resource
    isolation, and is a maintenance commitment.
  - *External-service plugin* — a connector to a hosted Transkribus
    REST API. Cleanest but binds to a single commercial vendor.
- **Format priority**. ALTO is the W3C-ish lingua franca and the
  default Transkribus / Kraken / Tesseract output; PAGE XML is
  PRImA's competitor, used heavily by Transkribus power users.
  Both are XML, both convertible. Implement ALTO first (smaller
  schema, broader adoption); PAGE second.
- **Confidence threshold defaults**. Most ALTO outputs include a
  `WC` (word confidence) attribute as a [0,1] float. A sensible
  default is "auto-accept ≥ 0.95, auto-reject < 0.50, queue the
  rest" — but the cutoff varies by engine and corpus, so it must
  be adjustable per import session.
- **Image storage at scale**. A 5,000-image corpus at 5 MB
  per page is ~25 GB. The current media folder approach
  (filesystem under `media_dir`) handles this in principle but
  needs a chunked / resumable upload to survive flaky connections
  and an async background ingestion job (the synchronous
  `await file.read()` pattern from
  [Security review 2026-04-27 §2](Security_review_2026-04-27.md)
  cannot be reused for batches this large).
- **Surface vs document**. A ten-image batch per document is
  trivial; a thousand-image batch *across documents* needs an
  ingestion model that creates documents on the fly.
  Recommendation: scope this feature to *one document at a time*
  in v1; cross-document batch import is a v2 concern.
- **Review queue persistence**. If the editor reviews 800 zones,
  closes the laptop, and resumes tomorrow, the partial state must
  survive. Sketch: a new `htr_import_session(id, document_id,
  status, accepted_zones, pending_zones, rejected_zones,
  created_at)` table — straightforward to add but needs a tasteful
  UI.

### Why deferred

- The current binding endpoint is enough for the (rare) editor
  who already runs Transkribus and can transform its output to the
  platform's JSON shape. That covers the "I have a custom pipeline"
  audience. The mass-corpus audience that the README implies is
  larger isn't there yet — the current Aracne2 deployments work on
  small editions where manual zone tracing is feasible.
- ALTO and PAGE parsers are the easy 30%; the review-queue UI is
  the 70%. Building it before a real corpus exercises it would
  almost certainly produce the wrong UX. Wait for the first
  project that actually has a thousand-image manuscript and design
  the queue with their editors in the room.

### Prerequisites

- The `<zone>` / `<surface>` / `<facsimile>` model already lives
  end-to-end ([ZONES_FACSIMILE.md](reference/ZONES_FACSIMILE.md)).
- The `POST .../zones/import` route already exists and is the
  natural promotion target — bump it from JSON-only to
  `Content-Type: application/xml` for ALTO / PAGE.
- The chunked-upload helper from
  [Security review 2026-04-27 §2](Security_review_2026-04-27.md)
  (`services/uploads.read_capped`) needs an asyncio-friendly
  variant for streamed image batches.

### Trigger for implementation

- An editor or EditorInChief explicitly asks for thousands-of-images
  HTR ingestion, **or**
- The first deployment lands a manuscript corpus where manual zone
  tracing would take more than a few weeks per editor.

Until either trigger fires, the current "JSON binding endpoint +
manual editor" coverage is the right level of investment.

*Added: 2026-04-29*

---

## 24. ~~`public_navigation` capability — auto-cabled links on the public site~~ ✅ Shipped

> Shipped 2026-05-02 as Milestone 1 item 4 of 5. See
> [Aracne_Roadmap.md](Aracne_Roadmap.md) for the implementation
> summary; the original design notes below are kept for reference.

🔴 High (historical priority)

Mirror the existing auto-cabling pattern (`inline_authority`,
`collection_deposit`, `website_deposit`) for the **public-facing
home + header + footer**. New capability `public_navigation` in
`PluginMeta` lets a plugin advertise that it ships a public page,
and the platform's public layout surfaces a link to it without any
hand-coded plugin-specific logic.

### Idea

`PluginMeta.ui_descriptor`:

```python
"public_navigation": {
    "component": "NlSearchPublicView",     # name in the SPA registry
    "url": "/search-nl",                   # path the link points to
    "label_it": "Cerca in linguaggio naturale",
    "label_en": "Natural-language search",
    "label_key": "nl_search.public_link_label",   # optional, wins over label_*
    "icon": "sparkles",                    # optional heroicon name
    "section": "header",                   # "header" | "home_quick_links" | "footer"
    "priority": 100,                       # tab sort key, lower = leftmost
}
```

### Frontend pieces

* New `frontend/src/components/public-pages/registry.ts` mirroring
  `LOOKUP_COMPONENTS` / `DEPOSIT_COMPONENTS` — maps the
  ``component`` string to a lazy-imported Vue component.
* `PublicLayout.vue` adds a route-level `<component :is>` that hosts
  the active plugin's view, inheriting the public theme,
  header / footer, and dark-mode handling automatically. The plugin
  ships a thin Vue page; PublicLayout owns the chrome.
* `PublicHeader.vue` / `PublicHomeSection.vue` / `PublicFooter.vue`
  iterate `pluginStore.plugins` filtered by capability + the
  matching `public_link_<plugin_name>_enabled` toggle in
  `system_settings`, sorted by `priority`. Section slot decides
  *where* the link lands.
* Admin → `Pagine Pubbliche` panel auto-generates a per-plugin
  toggle whenever a plugin advertising `public_navigation` is
  active. Default off — activating the plugin doesn't auto-publish
  its surface; the admin must consciously flip the toggle.

### Backend

* No new tables. Settings live in `system_settings`, keyed
  `public_link_<plugin_name>_enabled` (boolean string).
* Hot mount / unmount of the plugin makes the link appear /
  disappear in real time — same plumbing as today's plugin
  activate/deactivate route mounting.
* The page itself is a public route declared by the plugin's
  router (e.g. `GET /api/v1/<plugin>/...` for any data the SPA
  view needs). The SPA's PublicLayout fetches what the view
  declares.

### Consumers we already have on the radar

| Plugin | Path | What it does |
|---|---|---|
| `nl_search` (#25) | `/search-nl` | Natural-language search over the curated corpora — see the dedicated entry. |
| `public_maps` | `/map` | Visualises every indexed `placeName` entity on a Leaflet map. Tile provider configurable per deployment (OSM default; MapTiler / Mapbox / IIIF Maps optional with API key in encrypted system_settings). Public visitors browse / filter geographic occurrences and click through to the document where each toponym surfaces. Ideal for diplomatic-papers archives where geography is a primary access path. |
| `public_timeline` | `/timeline` | Horizontally-scrollable chronological view that surfaces dated events extracted from `<date>` elements + entities with date metadata. Supports zoom (century / decade / year) and click-through to the citing document. Useful for archives where the temporal axis is the primary navigation key — registers, chronicles, dated correspondence corpora. |
| `public_usage` | `/usage` | Aggregate, privacy-preserving usage statistics: pageviews, top-N collections, top-N entities, time-series of public reads. Renders charts via Chart.js; no per-user data collected. Operators get a public "see how often the corpus is consulted" page that doubles as an institutional metric for grant reporting. |

Each future plugin lands as a one-PR addition: declare the
capability + ship a Vue component + add a line to the registry.
Zero changes to PublicHeader / PublicHomeSection / PublicFooter.

### Open questions

- **Section slots fixed or extensible?** Three slots (header / home /
  footer) cover today's needs. Adding a fourth later means a
  one-line addition to the iteration logic; no refactor.
- **Per-instance only.** The whole capability is platform-wide —
  the SPA's PublicLayout has one navigation tree, not one per
  website. Websites that need their own AI / map / timeline must
  handle that inside the website renderer separately. Coherent
  with the decision that platform-level features (NL search,
  cross-corpus map, instance-wide timeline) live on the platform
  URL, not inside an exportable static site.
- **Layout slot for the link in `home_quick_links`.** The cover
  text WYSIWYG is owned by the admin — quick-links would render
  *below* it as a tile grid. Sketch the visual treatment when the
  primitive lands.

### Why deferred

Building the primitive without a second consumer is over-
engineering. The trigger to implement is the moment the **second**
plugin that wants public-page navigation lands. `nl_search` (#25)
is the natural first; `public_maps`, `public_timeline`, or
`public_usage` will likely be the second.

### Trigger for implementation

- A second plugin from the consumer list above gets prioritised, or
- An admin explicitly asks for the NL search link to appear in the
  public home page (which forces the primitive to ship alongside
  #25 instead of after).

*Added: 2026-04-29*

---

## 25. ~~Natural-language search plugin~~ ✅ Shipped

> Shipped 2026-05-03 as Milestone 1 item 5 of 5. See
> [Aracne_Roadmap.md](Aracne_Roadmap.md) for the phase-by-phase
> summary; the original design notes below are kept for reference.

🔴 High (historical priority)

> **Depends on #24** (`public_navigation` capability) for the public
> homepage link toggle. The plugin can ship without #24 — the
> `/search-nl` page is reachable by direct URL — but the
> "expose this surface to public visitors via the public home"
> story only lights up once the primitive is in place.

Non-native plugin `nl_search`. Public-facing chat-style search at
`/search-nl` on the platform's own URL. **Not** part of websites
(which can be exported as STATIC / HYBRID and served from nginx
elsewhere — a NL search needs a live LLM, so it can't survive the
export). **Not** embeddable in third-party sites. Lives in exactly
one place: the Aracne deployment that hosts it.

### Idea

The visitor types a question (*"i documenti che parlano del padre
di Carlo I"*); the plugin's backend orchestrator runs an LLM
tool-use loop against the **MCP server's existing read tools**
(imported as Python functions, no HTTP loopback), and returns a
synthesised answer + citations to real TEI documents (slug +
filename + excerpt).

The MCP layer's security boundary (corpus-scoped + public+
published) is reused as-is: the orchestrator constructs a
synthetic `McpAuthContext` from the plugin's config (which corpus
or set of corpora the public NL search exposes), and the same
`server.dispatch()` enforces the same filters that today gate
Claude Desktop tokens.

### Architecture sketch

```
Visitor (browser)
  │  POST /api/v1/nl-search/query
  │  { "query": "documenti che parlano del padre di Carlo I" }
  ▼
Plugin router
  │  rate-limit / auth gate / budget check / cache lookup
  ▼
Orchestrator (server-side)
  │  initial messages = system_prompt + user_query
  │  tools_manifest = subset of MCP tools (read-only):
  │    - search_entities, find_entity_occurrences
  │    - get_collection, list_documents
  │    - get_document_source / tei_to_text (capped)
  │  loop:
  │    LLM tool_call → app.plugins.mcp_server.server.dispatch()
  │      with McpAuthContext built from plugin config
  │    tool_result fed back to LLM
  │  emit final answer + citations
  ▼
SSE stream to browser
  { "answer_chunk": "...", "citations": [...] }
```

### Abuse mitigations (the part that matters)

The risks the maintainer explicitly flagged are:
- **Cloud provider** — anonymous traffic burns the API budget that
  was meant for the editorial team's AI panel.
- **Local Ollama** — anonymous traffic saturates server CPU / GPU
  and disables the editor's own AI sessions.

Mitigations the plugin ships:

| Setting | Default | Purpose |
|---|---|---|
| `nl_search_require_login` | **true** | Anonymous access disabled by default. Editors-only deployment is the safe posture. Operators who want public anonymous access opt-in. |
| `nl_search_provider` | `ollama` | Per-plugin override of the platform's AI provider — separates the budget pool. |
| `nl_search_api_key` | — | Per-plugin API key (Fernet-encrypted in `system_settings`). NL search consumes this, not the platform-wide `ai_*_api_key`. |
| `nl_search_daily_budget_eur` | `2.00` | Hard cap; once exceeded, endpoint returns 503 with a "resumes tomorrow" banner. |
| `nl_search_max_concurrent` | `2` | For Ollama: in-process semaphore. Request 3 either queues or 503s based on `nl_search_concurrency_overflow`. |
| `nl_search_rate_per_ip` | `3/min, 30/day` | slowapi limits, anonymous-mode only. |
| `nl_search_rate_per_session` | `10/hour` | Logged-in mode. |
| `nl_search_captcha_enabled` | `false` | Optional hCaptcha gate before first query of session. |
| `nl_search_query_timeout_s` | `30` | Per-query LLM timeout. |
| `nl_search_cache_ttl_minutes` | `60` | Identical-query cache (key = hash(query, corpus, provider)). |

The plugin is **off by default**; an admin must activate it via
`/admin/plugins`, configure provider + budget, and (if going
public) flip `require_login = false` consciously.

### Citation enforcement

The system prompt includes a hard rule:

> Cite only documents you have explicitly retrieved via tool
> calls in this conversation. Do not invent slugs or filenames.
> Each citation must be a `{slug, filename, excerpt}` object the
> tool result included verbatim.

This is the difference between "AI search that hallucinates URLs"
and "AI search that always grounds in the corpus". The plugin
post-validates: every cited `{slug, filename}` must appear in the
tool-call history; otherwise the citation is dropped.

### Frontend

A single Vue component `NlSearchPublicView.vue` registered in
`PUBLIC_PAGE_COMPONENTS` (the registry introduced by #24). It
hosts a textarea, an SSE-streamed response area with progressive
markdown rendering, and a citations strip below. Inherits the
public theme via PublicLayout — same chrome as the existing
search page.

If #24 ships, the plugin also declares `public_navigation` so the
admin can surface the link in the public homepage. If #24 hasn't
shipped yet, the plugin still works at direct URL `/search-nl`.

### Why deferred

- The MCP layer is barely a week old; we want a real editor
  workflow on top of it before deciding whether NL search is a
  shape that fits.
- The first deployment to use Aracne2 publicly will tell us
  whether anonymous public NL search is the right framing or
  whether editors-only is enough — that decision affects which
  abuse mitigations are mandatory vs optional.
- Cost projections (`$0.005`-ish per query on Sonnet, ~$5/day at
  1000 queries/day) need a real corpus to validate; on a small
  edition the queries-per-day will be much lower and the budget
  cap can be tighter.

### Trigger for implementation

- An editor or institution asks for natural-language search over
  the published corpus, **or**
- A deployment is sufficiently large that keyword search is no
  longer enough as the primary public access path, **or**
- An academic publisher wants to demo "AI-grounded TEI search" at
  a conference and asks for a polished surface.

*Added: 2026-04-29*

---

## 26. Non-native plugin: Matomo / Plausible analytics injector 🔵 To discuss

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
- §26 would be opt-in at install time, configured per-deployment,
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

*Added: 2026-04-23 — renumbered from §15 to §26 on 2026-04-29 to fix a duplicate-numbering glitch.*

---

## 27. Non-native plugin: `policy_pages` — institutional declarations as live forms 🔴 High

A non-native plugin that turns the institutional declarations an
operator must produce — mission, privacy / DPIA, storage policy,
continuity plan, CTS self-assessment, citation guide, editorial
board, etc. — into **live forms inside the platform**, with public
rendering, versioning, multi-locale support, and platform-side
auto-filled fields that re-read the running deployment's state.

Subsumes the four template-style deliverables previously planned
in [`CTS_COMPLIANCE_ROADMAP.md`](CTS_COMPLIANCE_ROADMAP.md) §3
(Storage Policy template), §4 (Continuity Plan template), and §5
(CTS self-assessment scaffold), plus the cross-cutting "where do
institutional declarations actually live?" question. The fifth
roadmap item — Fixity layer — is unrelated infrastructure and
stays as its own deliverable.

### Idea

Each declaration is a **template** (a Python module declaring a
list of `Field` objects); each filled-in instance is a
`policy_page` row whose `content_jsonb` carries the values. The
admin opens an empty template, fills the operator-supplied fields,
publishes; the platform renders a public Markdown page at
`/policies/<slug>` that the institution can link from anywhere
(including the public homepage's footer via the
[`public_navigation`](#) capability of §24).

### Built-in template catalogue (initial 12)

Each template is tagged with one or more categories so admins can
filter by relevance:

| Template | Categories | Platform-filled fields | Operator fields |
|---|---|---|---|
| `mission` | `core`, `cts:R1` | platform name, version | mission statement, scope, target community, durability commitment |
| `privacy_dpia` | `core`, `cts:R4` | PII fields the platform handles, retention defaults, IP-hashing status | data controller, DPO contact, lawful basis, takedown SLA |
| `storage_policy` | `cts:R9` | Postgres / eXist-db versions, Docker volumes, backup plugin status | off-site backup target, RPO / RTO, key custodian, restore-rehearsal cadence |
| `continuity_plan` | `cts:R3` | active deposit plugins, OAI-PMH endpoint, current backup retention | designated successor institution(s), DOI redirection procedure, communication plan |
| `cts_self_assessment` | `cts:meta` | per-requirement platform-contribution paragraphs (auto-pulled from CTS_COMPLIANCE_ROADMAP) | per-requirement institutional declarations |
| `funding_staffing` | `core`, `cts:R5` | — | funding sources, staffing roles, succession arrangements |
| `expert_directory` | `core`, `cts:R6` | — | named experts (multi-row form: name, role, contact, expertise area) |
| `appraisal_policy` | `cts:R8` | currently-published collection count, schema catalogue | acceptance criteria, rejection criteria, deaccessioning procedure |
| `preservation_plan` | `cts:R10` | TEI version in use, schema catalogue, deposit-target list | preservation horizon, format-migration plan, format-normalisation policy |
| `incident_response` | `cts:R16` | security review file list, Dependabot status | incident contacts, escalation ladder, disclosure timeline |
| `citation_guide` | `core` | DOI badge present yes/no, JSON-LD schema.org markup status | suggested citation format per collection, attribution expectations |
| `editorial_board` | `core` | — | board membership (multi-row), advisory committee, governance |

Operators that don't pursue CTS use the `core`-tagged subset and
ignore the `cts:*` ones. CTS-pursuing operators activate every
`cts:R*` template and get the entire institutional declaration
body in one place.

### Platform pre-fill — the brilliant part

Every `Field` object can declare itself as `platform`-sourced:

```python
TEMPLATE = PolicyTemplate(
    slug="storage_policy",
    title_key="policy.storage.title",
    categories=["cts:R9"],
    fields=[
        # Platform-filled (read-only on the operator's form;
        # re-evaluated at render time).
        Field("postgres_version",  source=lambda: platform.postgres_version()),
        Field("existdb_version",   source=lambda: platform.existdb_version()),
        Field("docker_volumes",    source=lambda: platform.docker_volume_list()),

        # Operator-filled.
        Field("offsite_target", kind="text", required=True,
              hint_key="policy.storage.offsite_target_hint"),
        Field("rpo_hours", kind="integer", required=True,
              min=1, max=168),
        Field("rto_hours", kind="integer", required=True,
              min=1, max=720),
        Field("key_custodian", kind="text", required=True),
        Field("restore_rehearsal_cadence", kind="enum",
              options=["monthly", "quarterly", "annually"]),
    ],
    public_template="storage_policy.md.j2",
)
```

When the operator opens the form, platform-sourced fields are
rendered greyed-out with their current value. When the deployment
state changes (e.g., admin upgrades eXist-db), the public
`/policies/storage-policy` re-reads the value at render time —
**the policy auto-updates without anyone touching it**. A property
that static Markdown templates cannot have.

### Versioning + audit

Every save creates a `policy_page_versions` row capturing the full
`content_jsonb`, the actor user, the timestamp, and a content hash.
The public page footer renders *"Version 3, published by X on
2026-Q3, supersedes v2 of 2026-Q1"* — exactly the audit trail a
CTS reviewer expects.

No draft / review workflow: per the maintainer's call, policy
content arrives at the admin's desk pre-approved by the
institution's external policy process. The platform's job is to
**transcribe** approved policies, not to host the policy
deliberation.

### `PolicyManager` capability role — single holder, not workflow

A new **capability role** (orthogonal to the existing hierarchical
roles `User` / `Editor` / `Designer` / `EditorInChief` / `Admin`).
Admin can grant `PolicyManager` to any user from `User` upwards;
the granted user gains read+write access to the
`policy_pages` admin surface independent of their main role.

> **Singleton constraint**: at any moment **at most one user** in
> the deployment holds `PolicyManager`. Granting it to user B
> while user A already has it auto-revokes A's role first
> (recorded in the audit log as a transfer, not as two unrelated
> events). Rationale: a single named accountability holder for
> institutional policy content matches the way real organisations
> assign that responsibility, and removes ambiguity if two
> simultaneous holders disagree on a policy edit.

Implementation:

- New row in the `roles` table:
  `(name="PolicyManager", description="Edits institutional policy pages",
   kind="capability", singleton=True)`. The `kind` and `singleton`
  columns are new on the `roles` table; the existing five
  hierarchical roles are migrated as `kind="hierarchical",
  singleton=False` by default.
- The existing many-to-many `user_roles` is reused. Singleton
  enforcement happens at the service layer when the assignment
  is granted: a transactional `transfer_singleton_role(role_name,
  to_user_id)` revokes the role from any current holder and
  grants it to the target in the same transaction; the audit log
  captures both legs.
- A new dependency `require_capability("PolicyManager")` for the
  `/admin/policies/*` endpoints, distinct from the hierarchical
  `require_role(min_role=...)` used elsewhere.
- Admin role-management UI changes for capability roles: instead
  of a checkbox per user, the UI shows a single dropdown
  *"Current Policy Manager: [user X]"* with a Change button that
  opens a user-picker. Reassignment is one click; the previous
  holder is shown a notification when they lose the role.

The pattern (capability role, optionally singleton) is generic:
future capability roles can declare themselves singleton or
multi-holder as appropriate. Examples that might be **multi-holder**:
`Translator`, `Annotator`, `BibliographyReviewer`. `PolicyManager`
is the first singleton.

### Multi-locale (IT / EN)

Every operator field has an `it` and `en` value side by side. The
public page is served at `/policies/<slug>?lang=it` (or based on
the visitor's `Accept-Language`). The form editor shows tabs for
each configured locale; missing translations fall back to the
default locale with a banner ("Italian translation not available").

The platform-filled fields are language-agnostic (versions,
volume names) so they appear identical across locales.

### PDF export

Each published policy gets a `?format=pdf` variant:
- markdown → HTML (already done by the public render)
- HTML → PDF via `weasyprint` (Python, no headless browser
  dependency)
- Includes version metadata, signed-by footer, deployment
  fingerprint (URL + date)

CTS reviewers and institutional archivists frequently want PDFs
for offline retention. ~1 day of work on top of the core plugin.

### Public navigation integration

The plugin declares the `public_navigation` capability of
[FUTURE_IDEAS §24](#24-public_navigation-capability) and renders
either:
- a "Policies" footer link → `/policies` index, or
- per-policy header / footer links if the admin opts in for
  individual policies (e.g. "About" → `/policies/mission`).

The toggle lives in the per-policy admin form, not platform-wide,
so admins can publish 12 policies but link only 3 in the footer.

### Surfaces

```
backend/app/plugins/policy_pages/
├── plugin.py
├── router.py                  # /admin/policies + /policies
├── service.py                 # CRUD + versioning + render
├── pdf.py                     # weasyprint integration
├── templates/                 # built-in policy templates (Python)
│   ├── _base.py               # PolicyTemplate / Field dataclasses
│   ├── mission.py
│   ├── privacy_dpia.py
│   ├── storage_policy.py
│   ├── continuity_plan.py
│   ├── cts_self_assessment.py
│   ├── funding_staffing.py
│   ├── expert_directory.py
│   ├── appraisal_policy.py
│   ├── preservation_plan.py
│   ├── incident_response.py
│   ├── citation_guide.py
│   └── editorial_board.py
├── public_md/                 # Jinja2 markdown templates per policy
└── tests/

frontend/src/views/admin/PolicyPagesView.vue       # list + form editor
frontend/src/views/public/PolicyPagePublic.vue     # renderer
frontend/src/components/policy-pages/FieldRenderer.vue  # per-Field type
```

### Effort

| Step | Effort |
|---|---|
| Plugin scaffold + Alembic + base model + versioning | 2g |
| `PolicyTemplate` / `Field` declarative engine + 12 built-in templates | 4g |
| Platform pre-fill mechanism (lazy re-evaluation at render) | 1g |
| Admin form-editor UI (multi-locale tabs + per-field-type renderer) | 2g |
| Public render + sitemap integration + JSON-LD | 1g |
| `PolicyManager` capability role + admin role-mgmt UI update | 1.5g |
| PDF export via weasyprint | 1g |
| Tests + help doc | 2g |
| **Totale** | **~14.5g** |

### Why deferred

- Sprint 1 and Sprint 2 ship without static template scaffolds for
  CTS — the operator that wants to certify between sprints uses
  external Word / PDF policies as today. The plugin lands in a
  dedicated Sprint 3.
- A real first-deployment will tell us whether the 12 built-in
  templates are the right list (probably we'll add 1-2 and prune
  1-2 based on actual operator feedback). Building the engine
  before the first user is a known over-design risk.

### Trigger for implementation

- The first institution preparing a CTS application asks for the
  policy surface inside Aracne, **or**
- A maintainer cycle has the bandwidth post-Sprint 2 and decides
  to invest in the institutional surface as a differentiator
  before recruiting new deployments.

### Why this is 🔴 High

It promotes Aracne2 from "TEI editorial CMS" to "TEI editorial CMS
+ institutional-declaration platform" — the latter is a
differentiator for repository-trust certifications (CTS, CoreTrustSeal,
CLARIN, nestor) that exists in **no other TEI tool today**, as far
as we know. Pairs naturally with the AI / MCP positioning to make
Aracne2 the obvious choice for institutions building durable,
auditable digital editions.

*Added: 2026-04-29*

---

## 28. Non-native plugin: LEAF Turning Engine — TEI ↔ Markdown, Transkribus → TEI 🟡 Medium

A non-native plugin that wraps the **Turning Engine** REST
microservice from the LEAF-VRE project (Linked Editing Academic
Framework — [leaf-vre.org](https://www.leaf-vre.org/), source at
[gitlab.com/calincs/cwrc/leaf](https://gitlab.com/calincs/cwrc/leaf/leaf-base-i8),
AGPLv3) to gain three transformations Aracne2 doesn't have natively:

- **TEI → Markdown** — for editors that want to publish a parallel
  version on Hugo / Jekyll / GitHub Pages / academic Substack-style
  surfaces. Today Aracne2 produces TEI → HTML via XSLT but no
  Markdown export path.
- **Transkribus → TEI** — directly relevant to the HTR pipeline
  (§23). Transkribus exports PAGE / ALTO XML; the Turning Engine
  has the conversion to TEI already implemented and battle-tested
  on real corpora. Adopting it cuts the §23 work from "write a
  PAGE/ALTO parser from scratch" to "POST the file at the Turning
  Engine, get TEI back".
- **TEI ↔ HTML** — already done in Aracne2 via XSLT, but the
  Turning Engine's variant is a useful fallback for cases the
  generic XSLT doesn't cover (or for editions that want a
  Turning-Engine-canonical serialisation).

### Architecture

The Turning Engine is itself a FastAPI Python microservice with
documented Swagger endpoints (`/v1/transform-file`,
`/v1/transform-string`). Containerised, AGPLv3, deployable
independently of the rest of LEAF (no Drupal / Islandora / Fedora
required).

The plugin in Aracne2 is a thin proxy:

```
backend/app/plugins/leaf_turning_engine/
├── plugin.py
├── router.py            # /api/v1/leaf-turning/{tei-to-md, transkribus-to-tei, ...}
├── service.py           # httpx async calls to the configured endpoint
├── schemas.py
└── tests/

frontend/src/components/plugins/LeafTurningEngineConfig.vue
  # admin: base_url + health check button
```

Settings (Admin only):
- `leaf_turning_base_url` — URL of the Turning Engine instance
  (operator runs their own container, or points at a public one
  if LEAF offers it).
- `leaf_turning_request_timeout_s` — default 30s.
- `leaf_turning_max_input_bytes` — default 10 MB. The Turning
  Engine is itself rate-limited and resource-bounded, but
  defending the proxy is cheap insurance.

Editor surface:
- Document detail → "Esporta come Markdown" button (calls
  TEI → Markdown).
- HTR import flow (when §23 ships) → "Importa da Transkribus"
  delegates the PAGE/ALTO → TEI step to the Turning Engine.

### Why Medium

Direct value depends on:
1. **TEI → Markdown**: useful but not blocking — a project that
   wants Markdown export today can use external tools. Nice to
   have natively.
2. **Transkribus → TEI**: high value if §23 (HTR pipeline) lands
   first; otherwise it's an isolated import path with no consumer.
3. **TEI ↔ HTML**: low marginal value — Aracne2's XSLT path is
   the primary route.

The plugin earns its keep mainly as an **enabler for §23**. If
the HTR pipeline never lands, this plugin's value is the
TEI → Markdown export alone, which is real but doesn't justify
~3-4 days on its own.

### Strategic note — LEAF is a competitor, not a partner

LEAF-VRE and Aracne2 occupy the **same conceptual space**: a
TEI-aware editorial CMS for academic digital editions. They run
on completely different stacks (LEAF on Drupal + Islandora +
Fedora; Aracne on Python + FastAPI + Postgres + eXist-db) and
target overlapping audiences. An institution evaluating digital-
edition platforms picks one or the other.

Wrapping the Turning Engine is a *tactical pick* of a
genuinely useful LEAF component, not an endorsement of LEAF as a
whole. The AGPLv3 license requires attribution and source
availability for derivative works, but a plugin that only
*calls* the Turning Engine via HTTP API is not a derivative
work — it's a client. Standard separation. The plugin's
help doc should still cite the LEAF project clearly, both as a
courtesy and as a research-community good citizen move.

### Effort

| Step | Effort |
|---|---|
| Plugin scaffold + httpx client + auth (none, Turning Engine is unauthenticated by default) | 0.5g |
| Three endpoint proxies + Pydantic request/response schemas | 1g |
| Editor UI button (Esporta Markdown) | 0.5g |
| Integration with §23 HTR flow (when §23 lands) | overlap with §23 |
| Health check / fallback when endpoint is down | 0.5g |
| Tests (httpx.MockTransport) + help doc | 1g |
| **Totale (standalone)** | **~3.5g** |

### Trigger

- §23 (HTR pipeline) is promoted to a milestone — at that point
  this plugin lands as part of §23's import path, **or**
- An editor explicitly asks for TEI → Markdown export, **or**
- LEAF publishes a hosted public Turning Engine endpoint (today
  the README assumes self-hosting), making the plugin one-click
  to use without operator infrastructure.

Until any of these fires, this is a tactical idea worth keeping
on the radar but not worth implementing speculatively.

*Added: 2026-04-30*

---

## 29. Server-side PDF renderer — opt-in sidecar service 🟡 Medium

A new optional Docker container (compose profile `pdf`) that
wraps `weasyprint` (or equivalent CSS-paged-media engine) behind
a tiny FastAPI surface. The backend posts HTML or Markdown to it,
gets back a PDF byte stream. The image grows by ~80 MB only on
deployments that opt in; default deployments keep using the
browser's built-in **Print → Save as PDF** path that every
PDF-producing surface already supports today.

### Why a sidecar (and not a Python dep)

Aracne2's plugin activation toggle does NOT install dependencies
at runtime — every plugin's deps are baked into the image at
build time. Adding `weasyprint` to `requirements.txt` ships ~3 MB
of Python wheel **plus the system libs the wheel needs at
import time** (`cairo`, `pango`, `gdk-pixbuf`, `fontconfig` —
~80 MB of `apt` packages) into every backend image regardless
of whether the operator ever asks for a server-rendered PDF.

A sidecar (separate container with its own image) lets the
operator decide at compose time:

```yaml
services:
  pdf:
    profiles: ["pdf"]
    image: aracne2-pdf:latest
    # ...
```

Deployments that omit `--profile pdf` never start the container
and never download its image. Same pattern already in use for
the Postfix container (`profiles: ["email"]`, M1 §11).

### Why it's platform-wide and not policy-specific

Browser print-to-PDF works for **every** read-only public surface
Aracne2 already exposes:

- public document view (TEI document)
- public bibliography
- public entities pages
- public policy pages (M3 §27)
- audit-log CSV view (already ships CSV — PDF would be a luxury)
- collection deposit packets (Zenodo / IA / Codeberg / GH / GL /
  Dataverse) currently attach the publication's HTML or raw
  TEI; a server-rendered PDF would be an additional payload
  the deposit pipeline can offer

The sidecar is the **single substitute** for browser-print on any
of these surfaces — operators that want byte-for-byte deterministic
PDFs across browsers, embedded version-footer that the user
cannot strip by re-printing, and automation hooks (deposit
pipelines, nightly archive runs) flip the profile and gain it
everywhere at once.

### One deliberate exception: fully-static websites

The Websites module (`/sites/<slug>` + the static-export path)
ships HTML / CSS / JS to a directory the operator serves with
nginx without any Aracne2 backend at runtime. There is no
backend HTTP call available; the only path is the visitor's
browser print dialog. **Static websites stay on browser-print
only**, regardless of whether the sidecar is enabled — a
served-static export by definition cannot reach a sidecar API.

### Surfaces

```
sidecars/pdf/
├── Dockerfile               # weasyprint + system libs
├── pyproject.toml           # fastapi, weasyprint, jinja2
├── pdf_renderer/
│   ├── __init__.py
│   ├── main.py              # POST /render, GET /healthz
│   └── render.py            # html|md → PDF
└── tests/

backend/app/services/pdf_renderer.py
                              # thin httpx client; reads the sidecar
                              # URL from PDF_RENDERER_URL env or returns
                              # ``None`` if disabled (caller falls back to
                              # browser-print path)

docker-compose.yml            # `pdf` profile + service definition
.env.example                  # PDF_RENDERER_URL=http://pdf:8090
```

### Backend integration

Each PDF-producing feature exposes **two parallel UX paths**:

1. **Print-this-page button** — always present, uses the browser's
   `window.print()` plus a `@media print` stylesheet that hides
   admin chrome and bakes in a server-rendered version footer
   (no sidecar needed).
2. **Server-rendered PDF link** — present only when the
   `pdf_renderer` service is reachable. Visible as a small "PDF
   ufficiale" / "Official PDF" link next to the print button. The
   backend route hands the rendered HTML to
   `pdf_renderer.render()`, returns the PDF bytes with proper
   `Content-Disposition` and the deployment fingerprint stamped
   into the PDF /Producer metadata field.

A `GET /api/v1/system/pdf-renderer-status` endpoint lets the
SPA know whether to render the second path or hide it.

### Why not part of M3

The browser-print path covers "voglio il PDF della Storage Policy
del 15 settembre" perfectly fine for a single-deployment editor.
The sidecar's value materialises only when an operator hits one
of three triggers:

- a CTS reviewer asks for byte-for-byte deterministic PDFs;
- the deposit pipeline (Zenodo / IA) wants a server-rendered PDF
  attached automatically;
- a multi-policy / multi-document export job wants to script PDF
  generation without a human at the browser.

Until at least one of those triggers fires we ship browser-print
everywhere — same code path everywhere, zero new infra.

### Effort

| Step | Effort |
|---|---|
| Sidecar Dockerfile + FastAPI service + healthcheck | 0.5g |
| `services.pdf_renderer` httpx client + status endpoint | 0.5g |
| Wire each existing PDF-producing surface to the dual UX path | 1g |
| `@media print` stylesheets + version footer per surface | 0.5g |
| Tests (sidecar unit + backend integration with MockTransport) | 0.5g |
| Docs + help-doc page on the toggle | 0.25g |
| **Totale** | **~3.25g** |

### Trigger for implementation

- A first deployment asks for deterministic PDFs of policy pages
  (CTS reviewer requirement), or
- The deposit pipeline (Zenodo / IA / Codeberg) gains a step that
  wants a PDF attached server-side, or
- An institution explicitly asks for "official PDF" semantics on
  any public page.

*Added: 2026-05-03*

---

*Last updated: 2026-05-03*
