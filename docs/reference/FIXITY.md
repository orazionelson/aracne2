# Fixity layer

## Overview

The fixity layer is Milestone 2's CTS R7 deliverable: per-document
SHA-256 records that the platform re-checks on a schedule and
surfaces drift in `/admin/fixity`. Closes the most visible CTS
reviewer gap on R7 — Aracne2 already had per-version SHA-256
fingerprints in `document_versions.content_sha256` (M1, Alembic
0072), but had no scheduled re-check / drift report until now.

For the user-facing how-to (where the page lives, what the
"Recheck now" button does, how to read the dashboard) see
**Help → Reference → Fixity**, source
[`backend/help_docs/05-reference/05-fixity.md`](../../backend/help_docs/05-reference/05-fixity.md).

For the original CTS-roadmap discussion see
[CTS_COMPLIANCE.md](CTS_COMPLIANCE.md).

---

## Scope decision

The platform stores SHA-256 hashes for **every** version row in
`document_versions`. The fixity layer re-checks only **the latest
publication-origin version per (collection, filename)** pair —
much cheaper to sweep on a schedule, and what the public actually
serves. Per the M2 brainstorm Q8 decision.

A drift in a non-publication row (a manual save the editor wrote
six months ago) is a different conversation: it has no public
exposure, and re-hashing every gzipped blob in the table on a
schedule would multiply storage I/O by 10–50× without delivering
proportional integrity value. If it ever becomes valuable, a
second sweep can be added in parallel.

---

## Data model

### Table `fixity_records`

```
fixity_records
─────────────────────────────
id                  UUID PK
collection_id       UUID FK → collections.id ON DELETE CASCADE
document_filename   VARCHAR(255)
expected_sha256     VARCHAR(64)        — hash recorded at deposit time
last_seen_sha256    VARCHAR(64) | NULL — hash observed on the last re-check
version_number      INT                — the publication version we re-check
size_bytes          INT                — uncompressed body size at deposit
status              fixity_status      — see enum below
first_recorded_at   TIMESTAMPTZ
last_checked_at     TIMESTAMPTZ | NULL
drifted_at          TIMESTAMPTZ | NULL — first transition into a drift state

UNIQUE (collection_id, document_filename)
```

**Source**:
[`backend/app/models/fixity_record.py`](../../backend/app/models/fixity_record.py),
[`backend/alembic/versions/0079_fixity_records.py`](../../backend/alembic/versions/0079_fixity_records.py).

### Enum `fixity_status`

| Value | Meaning |
|---|---|
| `ok` | Last re-check matched `expected_sha256` |
| `drifted` | Last re-check returned a different SHA-256 |
| `missing` | The expected `document_versions` row is gone (e.g. unpublish) |
| `error` | The body was unreadable (gzip / decode failure) |

---

## Service layer

`backend/app/services/fixity.py` — plain async functions, no class
wrapper. Public surface:

| Function | Purpose |
|---|---|
| `record_publication(db, *, collection, filename, expected_sha256, version_number, size_bytes)` | Upsert the row at deposit time. Resets a drifted row to `ok` and clears `drifted_at` when re-publication produces matching content. |
| `recheck_one(db, *, record)` | Re-hash the row's expected version row and transition status. Stamps `last_checked_at`; sets `drifted_at` on first `ok → drifted | missing`. |
| `recheck_all(db)` | Sweep every row in 200-row chunks; return per-status tally. |
| `list_records(db, *, page, per_page, status, collection_id)` | Paginated read for the admin view, sorted **drift-first** then most-recent check first. |
| `status_summary(db)` | Per-status row counts for the dashboard cards. |

### Drift-first sort

[`list_records`](../../backend/app/services/fixity.py) uses
`sqlalchemy.case` to assign a priority weight per status:

```python
status_priority = case(
    (FixityRecord.status == FixityStatus.drifted, 0),
    (FixityRecord.status == FixityStatus.missing, 1),
    (FixityRecord.status == FixityStatus.error, 2),
    (FixityRecord.status == FixityStatus.ok, 3),
    else_=4,
)
.order_by(status_priority, desc(FixityRecord.last_checked_at))
```

so the admin lands directly on what needs attention, no manual
filter needed.

### First-drift audit row

`_transition` writes exactly one `fixity.drift_detected` audit_log
row when a row transitions `ok → drifted` or `ok → missing`.
Subsequent re-checks while still drifted **do not** re-emit the
row — the operator sees one signal per drift event, not one per
re-check, so the audit log doesn't fill with duplicate entries
during a long-running drift.

The audit payload carries the canonical evidence:

```jsonc
{
  "collection_id": "8c2b…",
  "filename": "letter_001.xml",
  "expected_sha256": "ab12…",
  "last_seen_sha256": "ef34…",
  "new_status": "drifted",
  "version_number": 7
}
```

### Recording on publish

The publication path in
[`backend/app/services/xmldb.py`](../../backend/app/services/xmldb.py)
calls `record_publication` from inside
`_snapshot_collection_documents` for every file it snapshots —
including the **dedup path** where `create_version` returns `None`
because the content was unchanged. In that case the helper
re-reads the latest `publication`-origin row and re-records the
fixity entry, so a fresh fixity-feature deploy backfills rows for
already-published documents on the next re-publish.

---

## Scheduler

`backend/app/core/scheduler.py:fixity_recheck` is the apscheduler
job. Cadence is configured by the `fixity_recheck_cadence` system
setting (`daily` or `weekly`, default `weekly`). The setting is
read at scheduler-registration time
([`register_jobs_async`](../../backend/app/core/scheduler.py)) so
an operator flip from Settings does take effect on the next
backend boot.

| Cadence | Cron trigger |
|---|---|
| `daily` | `cron`, `hour=3, minute=0` (every day at 03:00 UTC) |
| `weekly` (default) | `cron`, `day_of_week=sun, hour=3, minute=0` |

The job calls `recheck_all` and logs the per-status tally:

```
fixity_recheck_done ok=412 drifted=0 missing=2 error=0
```

For ad-hoc spot-checks an Admin can also click **Recheck now** in
the UI which runs `recheck_all` synchronously and returns the
tally as the response body.

---

## REST API surface

All under `/api/v1/fixity`, all Admin-gated. Source:
[`backend/app/routers/fixity.py`](../../backend/app/routers/fixity.py).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/fixity` | Paginated, drift-first list. Filters: `status`, `collection_id` |
| `GET` | `/fixity/summary` | Per-status counts (drives the dashboard cards) |
| `POST` | `/fixity/recheck` | Synchronous full sweep; returns per-status tally |

### Drift-first response shape

```jsonc
{
  "data": [
    {
      "id": "8c2b…",
      "collection_id": "ab21…",
      "document_filename": "letter_001.xml",
      "expected_sha256": "ab12…",
      "last_seen_sha256": "ef34…",
      "version_number": 7,
      "size_bytes": 12456,
      "status": "drifted",
      "first_recorded_at": "2026-04-15T10:00:00Z",
      "last_checked_at":   "2026-05-03T03:00:00Z",
      "drifted_at":        "2026-05-03T03:00:00Z"
    },
    …
  ],
  "pagination": { "page": 1, "per_page": 50, "total": 1, "total_pages": 1 }
}
```

---

## Frontend

| Path | Role |
|---|---|
| [`frontend/src/stores/fixity.ts`](../../frontend/src/stores/fixity.ts) | Pinia store — paginated rows, summary cards, recheck-now flag |
| [`frontend/src/views/admin/FixityView.vue`](../../frontend/src/views/admin/FixityView.vue) | 4 status cards + drift-first table + Recheck-now button |

### Layout

- **4 dashboard cards** (`ok`, `drifted`, `missing`, `error`) at
  the top — clickable: clicking a card filters the table to that
  status; clicking again clears the filter.
- **Drift banner** (red) when the sum of non-`ok` rows is > 0.
- **Table**: status badge, document filename, expected hash
  (truncated with full value on hover), observed hash, version,
  last-checked time. The drifted row's observed hash is
  highlighted in red.
- **Recheck now** button at the top right — synchronous, refreshes
  the cards + first page of the table on completion.

The view is wired into the admin sidebar under "Amministra" via
`labelKey: nav.fixity`.

---

## Drift remediation

By design (per M2 brainstorm Q7) drift is **record-only**: the
platform never auto-quarantines a public render on a hash mismatch.
The Admin sees the drift, investigates, and decides:

- If the `document_versions` row was tampered with intentionally
  (e.g. a manual blob-level cleanup), they re-publish the
  collection so the canonical hash is re-recorded; the row
  transitions back to `ok` on the next re-check (or immediately
  via Recheck now).
- If the tamper is unauthorised, that's an incident — the audit
  log row + the drift snapshot are the evidence; the recovery
  involves restoring from a publication snapshot or a deposit
  backend (Zenodo / Internet Archive / …).

Auto-quarantine was deliberately not shipped: it is irreversible-
ish and risks taking down a published collection on a false
positive (e.g. an in-progress migration). It can be added later
if a deployment asks for it.

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/tests/test_fixity.py`](../../backend/app/tests/test_fixity.py) | 8 tests — service-level transitions (record, refresh, ok/drift/missing, no double-audit) + endpoint-level (drift-first list, recheck tally) |

---

## Open follow-ups

- **Per-collection fixity badge** in the editor's collection detail
  view — out of scope for v1 (Q9: `/admin/fixity` only). Easy
  add-on once an editor asks for it.
- **eXist-db tree fixity**: a discrepancy between the eXist-db
  working tree and the `document_versions` blob is its own drift
  signal; this layer does not address it. Would need a second
  table; flagged for Milestone 3 or beyond.
- **Auto-quarantine on drift** — deliberately deferred (Q7).
