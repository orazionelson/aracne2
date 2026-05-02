# Document versioning

## Overview

Every TEI document in Aracne2 has a **version history**: an
append-only timeline of `document_versions` rows that captures the
working-tree state at editorially meaningful moments. Versions are
written automatically by workflow events (creation, submission,
rejection, publication) and explicitly by editors via "Save version"
or "Roll back to vN".

Versioning underpins three user-facing capabilities:

- **History panel** in the TEI editor — every change traceable to an
  actor, a timestamp, and an audit-log row.
- **Working / published split** — editors keep editing a published
  collection without taking the public site offline; the public sees
  the last `publication`-origin snapshot per document.
- **Stable permalinks** — `?version=N` URLs on public pages resolve
  only to `publication`-origin rows, so manual saves and rollbacks
  can never leak to anonymous visitors.

For the user-facing how-to see the in-app help page at
**Help → Editing → Versioning**, source
[`backend/help_docs/02-editing/06-versioning.md`](../../backend/help_docs/02-editing/06-versioning.md).

For the original design discussion (working/published split,
SHA-256 dedup, manual-vs-auto origin matrix) see
[DEFERRED.md §7](../DEFERRED.md).

---

## Data model

### Table `document_versions`

```
document_versions
─────────────────────────────
id                  UUID PK
collection_id       UUID FK → collections.id ON DELETE CASCADE
document_filename   VARCHAR(255)
version_number      INT          — monotonic per (collection, filename)
xml_content         BYTEA        — gzip-compressed body
content_sha256      VARCHAR(64)  — SHA-256 of the *uncompressed* body
size_bytes          INT          — uncompressed size
origin              version_origin ENUM
message             TEXT NULL    — required for ``manual``
created_at          TIMESTAMPTZ
created_by_id       UUID FK → users.id ON DELETE SET NULL
audit_log_id        BIGINT FK → audit_log.id ON DELETE SET NULL

UNIQUE (collection_id, document_filename, version_number)
```

**Source**: [`backend/app/models/document_version.py`](../../backend/app/models/document_version.py),
[`backend/alembic/versions/0072_document_versions.py`](../../backend/alembic/versions/0072_document_versions.py).

### Enum `version_origin`

| Value | Trigger | Dedup | Deletable |
|---|---|---|---|
| `creation` | First write of a document | yes | no |
| `manual` | Editor pressed **Save version** | no | yes (Editor or Admin) |
| `submission` | Collection moved to *Review* | yes | no |
| `rejection` | EiC clicked **Request revisions** | yes | no |
| `publication` | EiC published the collection | yes | no |
| `rollback` | Editor restored a prior version | no | no |

"Dedup yes" means the row is **not** written when the new content's
SHA-256 matches the previous version — workflow re-publishes of
unchanged content do not bloat the table. `manual` and `rollback`
always write, so the editor sees the row they expect.

### Column `collections.last_published_tree_hash`

Migration [`0071_collections_last_published_tree_hash.py`](../../backend/alembic/versions/0071_collections_last_published_tree_hash.py)
adds a hex column populated when a collection is published. It is
the SHA-256 of the JSON-encoded `{filename: content_sha256}` map of
the working tree at publish time and lets the UI show "the editor
has unpublished changes since the last release" without diffing
every file.

### eXist-db layout — working / published split

The eXist-db filesystem mirror has two roots:

```
/db/aracne2/collections/{slug}/   ← working tree (editor view)
/db/aracne2/published/{slug}/     ← public snapshot (last publish)
```

Editors always write to the working tree. The public renderer reads
from the published tree. **Publish** copies the working tree to the
published tree atomically. **Unpublish** removes the published tree.

| eXist helper | Purpose |
|---|---|
| `published_path(slug)` | Return the published-tree URI for *slug* |
| `copy_collection_to_published(slug)` | XQuery-driven copy used by publish |
| `list_published(slug)` | List documents currently public |
| `get_published_document(slug, filename)` | Read the public XML body |

**Source**: [`backend/app/db/existdb.py`](../../backend/app/db/existdb.py),
[`backend/app/xqueries/system/copy_to_published.xq`](../../backend/app/xqueries/system/copy_to_published.xq).

---

## Service layer

`backend/app/services/document_versions.py` is the single entry
point. Plain async functions, no class wrapper.

| Function | Purpose |
|---|---|
| `create_version` | Stage a new row. SHA-256 dedup unless `skip_dedup=True`. Returns `None` on dedup hit. |
| `list_versions` | Per-(collection, filename) timeline, newest first; optional `?origin=` filter. |
| `get_version` / `get_version_content` | Read a single row's metadata or decompressed body. |
| `get_public_version` | Same as `get_version` but rejects non-`publication` rows — backs the public `?version=N` permalink. |
| `get_last_publication` | Most recent `publication` row for a document; used by the M2 fixity scheduler and the public renderer. |
| `manual_save` | Editor+ "Save version" — enforces the per-document soft cap. |
| `rollback_to` | Constructive rollback: writes the target body back to the working tree and appends a `rollback` row. Never destructive. |
| `compute_version_diff` | Unified text diff between two stored versions (`difflib.unified_diff`). |
| `delete_manual_version` | Remove a `manual` row only — auto rows are append-only. |
| `acquire_doc_lock` | PG advisory lock keyed on `(collection_id, filename)` — prevents concurrent writers from clobbering HEAD. No-op on SQLite. |

### SHA-256 dedup

```python
digest = hashlib.sha256(xml_bytes).hexdigest()
latest = await _latest_for_document(db, collection.id, filename)
if latest is not None and not skip_dedup and latest.content_sha256 == digest:
    return None  # workflow event on unchanged content — skip
```

This is what keeps the table free of "publish on unchanged content"
noise after the EiC re-clicks Publish without editing anything.

### Soft cap on manual versions

Reads `system_settings.document_manual_versions_max` (default `50`).
On overflow `manual_save` raises `ManualVersionsLimitReached(409)`;
the editor must delete an existing manual row to make room.

### Document lock

`acquire_doc_lock` calls
`pg_try_advisory_xact_lock(hashtextextended(...))` with key
`aracne.doc:{collection_id}:{filename}`. Lock is transaction-scoped
so it releases on COMMIT/ROLLBACK. Two writers on the same document
serialise; writers on different documents (or different collections)
never block each other. A 409 `DOCUMENT_BUSY` translates to a
"someone else is saving — retry" toast in the UI.

---

## REST API surface

All endpoints sit under the native `collections` plugin and require
**Editor+** unless noted. Source:
[`backend/app/plugins/_native/collections/router.py:572+`](../../backend/app/plugins/_native/collections/router.py#L572).

| Method | Path | Role | Purpose |
|---|---|---|---|
| `GET`    | `/collections/{id}/documents/{filename}/versions` | E+ | List versions, newest first. `?origin=` filter optional |
| `GET`    | `/collections/{id}/documents/{filename}/versions/{n}` | E+ | Metadata of a single version |
| `GET`    | `/collections/{id}/documents/{filename}/versions/{n}/content` | E+ | Raw XML body (decompressed, `application/xml`) |
| `POST`   | `/collections/{id}/documents/{filename}/versions` | E+ | **Save version** — body `{message: str}`, returns 201 |
| `POST`   | `/collections/{id}/documents/{filename}/versions/{n}/rollback` | E+ | Restore body of `vN` and append a `rollback` row |
| `DELETE` | `/collections/{id}/documents/{filename}/versions/{n}` | author or A | Delete a `manual` row only (422 `VERSION_NOT_DELETABLE` on auto rows) |
| `GET`    | `/collections/{id}/documents/{filename}/versions/{n}/diff?against=M` | E+ | Unified text diff between `vN` and `vM` |

### Public `?version=N` permalink

The public renderer accepts a `version` query parameter:

```
GET /public/{slug}/{filename}?version=3
```

Resolves via `get_public_version`: returns 404 if the version does
not exist OR if it exists but is not `publication`-origin. Manual
saves and rollbacks are never visible at this URL.

---

## Frontend

| Path | Role |
|---|---|
| [`frontend/src/stores/documentVersions.ts`](../../frontend/src/stores/documentVersions.ts) | Pinia store — list, save, rollback, diff |
| [`frontend/src/components/ui/VersionHistoryPanel.vue`](../../frontend/src/components/ui/VersionHistoryPanel.vue) | Drawer in the TEI editor showing the timeline |
| [`frontend/src/components/ui/SaveVersionDialog.vue`](../../frontend/src/components/ui/SaveVersionDialog.vue) | Modal capturing the manual-save message |
| [`frontend/src/components/ui/DiffViewer.vue`](../../frontend/src/components/ui/DiffViewer.vue) | Renders the unified diff from `?against=` |

The TEI editor exposes a **History** button. The drawer lists every
version (origin badge, message, author, timestamp), with per-row
actions: view body, diff against current, roll back. A toggle
filters to publication-origin only — the editor can quickly answer
"what did the public see at the time?".

---

## Hooks and audit log

Each version write produces an `audit_log` row whose `id` is
back-pointed by `document_versions.audit_log_id`. The reverse map
(audit row → version row) is the auditor's path: "who changed
*this* file *when* and what did the bytes look like before?".

| Audit action | Origin written |
|---|---|
| `document.created` | `creation` |
| `document.updated` | none — the editor must press **Save version** to capture an in-progress edit |
| `document.manual_save` | `manual` |
| `collection.submitted` | one `submission` per modified document |
| `collection.rejected` | one `rejection` per modified document |
| `collection.published` | one `publication` per modified document |
| `document.rollback` | `rollback` |

No new hook events were introduced — the existing collection-state
hooks fire the auto-snapshots from inside the workflow service.

---

## Configuration

| Setting key | Default | Effect |
|---|---|---|
| `document_manual_versions_max` | `50` | Per-document soft cap on `manual` rows. Raised in Admin → Settings if a corpus regularly hits it. |

Auto rows have **no** cap — the integrity record must remain
complete regardless of operator preference.

---

## Storage cost

Bodies are gzip-compressed at level 9. A typical TEI document
(50–200 KB raw) compresses to 5–20 KB on the wire. The
`size_bytes` column stores the **uncompressed** size so an admin
can chart total raw storage without decompressing every blob.

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/tests/test_document_versions.py`](../../backend/app/tests/test_document_versions.py) | dedup, version_number monotonicity, soft cap |
| [`backend/app/tests/test_document_versions_endpoints.py`](../../backend/app/tests/test_document_versions_endpoints.py) | all REST verbs, manual-only delete, role gating |
| [`backend/app/tests/test_publish_creates_published_snapshot.py`](../../backend/app/tests/test_publish_creates_published_snapshot.py) | working/published split, unpublish |
| [`backend/app/tests/test_public_version_permalink.py`](../../backend/app/tests/test_public_version_permalink.py) | `?version=N` rejects non-`publication` |
| [`backend/app/tests/test_document_version_diff.py`](../../backend/app/tests/test_document_version_diff.py) | unified diff round-trip |
