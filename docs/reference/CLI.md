# `aracne` CLI

## Overview

`aracne-cli` is a small Python package shipped in the monorepo at
[`cli/`](../../cli/). It exposes the `aracne` console command, a
headless tool that runs on an editor's laptop (not in the docker
container) and talks to a running Aracne2 deployment over HTTPS
using a **personal access token** (PAT) for authentication.

It currently covers the M1 acceptance criterion *"a new admin can
deploy Aracne2, generate a CLI export, restore it on a fresh
instance, and recover the previous content history"* through four
commands:

| Command | Purpose |
|---|---|
| `aracne login` | Capture a PAT and verify it against the host |
| `aracne whoami` | Print the user the saved PAT resolves to |
| `aracne import` | Bulk-upload `*.xml` files from a directory into a collection |
| `aracne export` | Download a collection as a ZIP (working tree, or `--as-of <date>`) |

For the user-facing how-to (install, where to paste the token, the
PAT card on the Profile view) see
**Help → Reference → Command-line tool**, source
[`backend/help_docs/05-reference/03-cli.md`](../../backend/help_docs/05-reference/03-cli.md).

For the original design discussion (why a directory in the
monorepo, why PAT instead of reusing MCP tokens, why
`--on-conflict=skip` as default) see
[TO_DO.md](../TO_DO.md).

---

## Distribution

Not on PyPI. The audience is invite-only and the install step is:

```bash
git clone https://github.com/orazionelson/aracne2.git
cd aracne2
pip install -e cli/
```

The console script `aracne` is registered through `pyproject.toml`:

```toml
[project.scripts]
aracne = "aracne_cli.cli:app"
```

---

## Personal access tokens (PATs)

The CLI authenticates with a long-lived bearer token issued from
the user's Profile view ("API tokens" card). PATs are a parallel
auth surface to JWT sessions: the same `acl.py` middleware that
guards the platform handles both, so every existing
`require_role(...)` guard works unchanged.

### Token format

```
aracne2_pat_<43 url-safe characters>
```

`PAT_PREFIX = "aracne2_pat_"` — fixed in
[`backend/app/services/personal_access_tokens.py`](../../backend/app/services/personal_access_tokens.py).
The prefix lets the auth middleware dispatch to the PAT path
**before** the JWT decoder runs.

The plaintext is shown to the issuer **once**, in the response of
`POST /users/me/tokens`. The DB stores only a bcrypt digest in
`personal_access_tokens.hashed_token` — same `hash_password` /
`verify_password` path used by MCP tokens.

### Data model

```
personal_access_tokens
─────────────────────────────
id              UUID PK
user_id         UUID FK → users.id ON DELETE CASCADE
label           VARCHAR(128)   — human description ("my-laptop")
hashed_token    VARCHAR(128)   — bcrypt digest, never plaintext
created_at      TIMESTAMPTZ
last_used_at    TIMESTAMPTZ NULL
revoked_at      TIMESTAMPTZ NULL  — soft delete

INDEX (user_id)
```

Migration:
[`backend/alembic/versions/0075_personal_access_tokens.py`](../../backend/alembic/versions/0075_personal_access_tokens.py).
Model: [`backend/app/models/personal_access_token.py`](../../backend/app/models/personal_access_token.py).

### Auth middleware integration

[`backend/app/middleware/acl.py`](../../backend/app/middleware/acl.py)
gains a third bearer branch placed **before** the JWT decode path:

```python
if credentials.credentials.startswith("aracne2_pat_"):
    user = await resolve_pat(db, credentials.credentials)
    if user is None:
        raise AuthenticationError("INVALID_PAT", "Invalid or revoked API token")
    request.state.user = user
    request.state.role = await get_active_role(db, user)
    # … falls through to the resolved-user request handler
```

Effect: the PAT inherits the issuer's role at request time. Every
existing role guard keeps working unchanged. A revoked token
returns 401 `INVALID_PAT` on the very next request.

`resolve_pat` walks the non-revoked rows of the table and
`verify_password`-checks each one. On a match it bumps
`last_used_at` so the Profile UI can show "last used 2 hours ago".

### REST API surface

All under `/api/v1/users/me/tokens`. Editor+ only — Users (level
1) get a 403, by design.

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/users/me/tokens` | – | List own non-revoked tokens (no plaintext) |
| `POST` | `/users/me/tokens` | `{label: str}` | `{id, label, token, created_at}` — `token` is plaintext, **shown once** |
| `DELETE` | `/users/me/tokens/{id}` | – | 204 (idempotent) |

**Source**:
[`backend/app/routers/users.py:140+`](../../backend/app/routers/users.py#L140),
[`backend/app/services/personal_access_tokens.py`](../../backend/app/services/personal_access_tokens.py),
[`backend/app/schemas/users.py`](../../backend/app/schemas/users.py).

The frontend pair:
[`frontend/src/stores/personalAccessTokens.ts`](../../frontend/src/stores/personalAccessTokens.ts),
the "API tokens" card in
[`frontend/src/views/auth/ProfileView.vue`](../../frontend/src/views/auth/ProfileView.vue).

---

## Configuration file

`~/.aracne/config.toml` — chmod `0600` on every write.

```toml
[default]
host = "https://aracne.example.org"
token = "aracne2_pat_..."

[work]
host = "https://aracne.work.example"
token = "aracne2_pat_..."
```

Each top-level table is a **profile**. `aracne login --profile=work`
upserts one; every command takes `--profile NAME` (default
`default`) to pick which one to use.

Tests override the config home via the `ARACNE_CLI_CONFIG_HOME`
environment variable so the developer's real `~/.aracne` stays
untouched.

**Source**: [`cli/aracne_cli/config.py`](../../cli/aracne_cli/config.py).

---

## Commands

### `aracne login`

```
aracne login --host URL [--profile NAME] [--json]
```

Interactive: `--host` is prompted if missing; the token is **always
prompted** (typer hidden input — no `--token` flag, leaking the
token through shell history would defeat the point). The pair is
verified with a `GET /auth/me` round-trip and only then written to
the config file.

### `aracne whoami`

```
aracne whoami [--profile NAME] [--json]
```

Smoke check: prints `username`, the active role, and the host. A
revoked token surfaces here as `401 INVALID_PAT`.

### `aracne import`

```
aracne import \
    --collection SLUG_OR_UUID \
    --dir PATH \
    [--on-conflict skip|overwrite|fail] \
    [--concurrency N] \
    [--profile NAME] \
    [--json]
```

- Walks `PATH` for `*.xml` files (no recursion in v1).
- Filename validation: `^[a-zA-Z0-9][a-zA-Z0-9_\-]*\.xml$` —
  exactly the regex the backend enforces, so invalid names fail
  fast on the client without burning a request.
- Existence check via `GET /collections/{id}/documents`, then
  per-file `POST` (create) or `PUT` (overwrite) under
  `/collections/{id}/documents/{filename}`.
- Concurrency: `concurrent.futures.ThreadPoolExecutor` over the
  file list, bounded by `--concurrency` (default 4, max 16).
- Default `--on-conflict=skip` so re-importing the same corpus
  leaves existing rows untouched.
- Output: rich progress bar; on any failure prints a per-file
  error and continues; final summary
  `OK: N, skipped: M, failed: K`.

### `aracne export`

```
aracne export \
    --collection SLUG_OR_UUID \
    --output PATH.zip \
    [--as-of YYYY-MM-DD | ISO-8601] \
    [--concurrency N] \
    [--profile NAME] \
    [--json]
```

- Fetches the doc list via `GET /collections/{id}/documents`.
- Without `--as-of`: each document is downloaded at its **working
  tree** state (the editor view). The CLI authenticates as the
  editor — by design it sees what they're working on, not
  necessarily what the public sees.
- With `--as-of`: each document is resolved client-side. The CLI
  walks `GET /collections/{id}/documents/{filename}/versions?origin=publication`,
  picks the row with the highest `version_number` whose
  `created_at <= as_of`, then downloads
  `/versions/{n}/content`. Documents with no `publication`
  snapshot at or before the requested date are **skipped** with a
  warning (they were probably added later).
- Output ZIP layout:

  ```
  {output}.zip
  ├── manifest.json     # {exporter, exporter_version, exported_at,
  │                     #  as_of, collection, documents:[{filename,
  │                     #  version_number, sha256, skipped_reason}]}
  └── documents/{filename}.xml
  ```

- The manifest's per-document `sha256` is the SHA-256 of the body
  bytes that landed in the ZIP — handy for restore-time fixity
  checks against the destination instance.

---

## Wire format

Every backend response is wrapped in `{"data": ...}` per
[API_FORMAT.md](API_FORMAT.md). The CLI's `ApiClient` unwraps the
envelope on `get` / `post` / `put` / `delete`, and surfaces
backend errors as `ApiError(code, message, status_code)` so tests
can assert on `code` (locale-independent SCREAMING_SNAKE_CASE)
rather than the user-facing message string.

**Source**: [`cli/aracne_cli/api.py`](../../cli/aracne_cli/api.py).

For raw bytes (XML bodies, ZIP exports) the client exposes
`get_raw()` which returns the underlying `httpx.Response` so the
caller gets `.content` without a JSON decode pass.

---

## Tests

Unit tests live under [`cli/tests/`](../../cli/tests/) and use
`httpx.MockTransport` so no real backend is required.

| File | Coverage |
|---|---|
| [`cli/tests/test_config.py`](../../cli/tests/test_config.py) | TOML round-trip, `0600` permissions on writes, profile not found |
| [`cli/tests/test_api.py`](../../cli/tests/test_api.py) | envelope unwrapping, `ApiError` shape, raw-body path |
| [`cli/tests/test_commands.py`](../../cli/tests/test_commands.py) | each command end-to-end against `MockTransport`; `--on-conflict` matrix; `--as-of` resolution; ZIP manifest shape |

Backend-side coverage of the auth path:
[`backend/app/tests/test_personal_access_tokens.py`](../../backend/app/tests/test_personal_access_tokens.py).

---

## Out of scope (deferred)

- `aracne validate` — offline schema check. Useful but not blocking.
- `aracne delete` collection / document — destructive ops stay UI-only.
- Full-history serialization (every `document_versions` row + audit log)
  — much bigger footprint, separate design conversation.
- PyPI publication — distribution stays `git clone && pip install -e cli/`
  while the audience is invite-only.
- Per-token scopes (e.g. `--scope=read-only`) — every PAT inherits the
  issuer's role for v1; finer scoping later if needed.
- Admin UI to view / revoke any user's PATs — Admin can already
  deactivate the user, which invalidates every session and PAT
  on the next request.
