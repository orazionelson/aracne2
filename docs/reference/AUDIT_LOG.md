# Audit log

## Overview

Aracne2 records every intentional, user-attributable action in the
`audit_log` table. The table has been populated by the platform
since day one (auth events, document edits, plugin activations,
settings changes, …) but Milestone 2 added the **admin-facing
view** at `/admin/audit-log` so an Admin no longer needs `psql` to
answer "who deleted X last week".

For the user-facing how-to (where the page lives, how to filter,
how to export) see the in-app help at
**Help → Reference → Audit log**, source
[`backend/help_docs/05-reference/04-audit-log.md`](../../backend/help_docs/05-reference/04-audit-log.md).

For the original spec see [TO_DO.md](../TO_DO.md).

---

## Data model

```
audit_log
─────────────────────────────
id                BIGINT PK (autoincrement)
action            VARCHAR(128)        — e.g. "collection.published"
actor_id          UUID FK → users.id ON DELETE SET NULL
actor_username    VARCHAR(64)         — denormalised for stable display after deletion
target_type       VARCHAR(64)         — "collection" | "user" | "document" | …
target_id         TEXT
target_label      TEXT                — human-readable (slug, filename, username)
ip_address        INET                — already SHA-256-hashed in production
user_agent        TEXT
payload           JSONB               — domain-specific context
occurred_at       TIMESTAMPTZ         — DEFAULT now()
```

**Source**:
[`backend/app/models/audit_log.py`](../../backend/app/models/audit_log.py).

### Indexes (Alembic 0078)

The admin view hits the table with three predictable shapes:

- latest-first by time (default landing query),
- by actor over a time range,
- by action over a time range.

A 90-day retention window in a busy multi-editor deployment can
reach low-millions of rows, so [`backend/alembic/versions/0078_audit_log_filter_indexes.py`](../../backend/alembic/versions/0078_audit_log_filter_indexes.py)
adds three composite btree indexes — every column ordered `DESC`
so the planner does not do a backward scan when
`ORDER BY occurred_at DESC` is the only sort the view ever issues.

| Index | Columns |
|---|---|
| `ix_audit_log_occurred_at_desc` | `(occurred_at DESC)` |
| `ix_audit_log_actor_id_occurred_at_desc` | `(actor_id, occurred_at DESC)` |
| `ix_audit_log_action_occurred_at_desc` | `(action, occurred_at DESC)` |

### Retention

`audit_log_retention_days` (system_setting, default `90`) drives an
`apscheduler` `purge_audit_log` job that deletes rows older than
the cutoff every night at 02:00 UTC. The retention is configurable
from Admin → Settings; the job re-reads it at every tick.

**Source**:
[`backend/app/core/scheduler.py:purge_audit_log`](../../backend/app/core/scheduler.py).

---

## Action vocabulary

Action strings are free-form `domain.verb` (e.g. `auth.login_success`,
`collection.published`). The admin view's filter dropdown is
**curated** — it only shows the canonical list rather than every
distinct value the table has ever seen, so a typo never leaks into
the UI.

The curated list lives in
[`backend/app/services/audit_log.py:KNOWN_ACTIONS`](../../backend/app/services/audit_log.py).
A new audit action lands here as a one-line addition the same time
it gets emitted in the codebase.

Currently shipped actions (~40):

```
auth.login_success / password_changed / password_reset_{requested,confirmed}
user.created / updated / deactivated / soft_deleted / self_deleted
user.role_assigned / role_revoked / avatar_uploaded / avatar_deleted
user.data_exported / impersonation_started
collection.created / updated / deleted / assigned / unassigned / reassigned
collection.permission_granted / permission_revoked
collection.submitted / rejected / published / direct_published / unpublished
document.uploaded / updated / deleted / zip_uploaded / zones_updated
document.version_saved / version_deleted / rolled_back
media.uploaded / deleted
plugin.activated / deactivated
fixity.drift_detected
```

---

## REST API surface

All under `/api/v1/audit-log`, all Admin-gated. Source:
[`backend/app/routers/audit_log.py`](../../backend/app/routers/audit_log.py).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/audit-log` | Paginated list, filtered |
| `GET` | `/audit-log/actions` | Curated dropdown vocabulary |
| `GET` | `/audit-log/{id}` | Single row + JSONB `payload` + user_agent |
| `GET` | `/audit-log/export.csv` | Stream CSV; same filters as list |

### `GET /audit-log` query parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `page` | int | `1` | ≥ 1 |
| `per_page` | int | `20` | 1–100 |
| `q` | str | – | Free-text — ILIKE `%q%` against `actor_username` / `action` / `target_label` (OR-of-three) |
| `actor_id` | UUID | – | Exact match on `audit_log.actor_id` |
| `actor_username` | str | – | ILIKE substring match |
| `action` | str | – | Exact match (drop-down value) |
| `target_type` | str | – | Exact match (e.g. `collection`) |
| `target_id` | str | – | Exact match |
| `from` | ISO-8601 | – | `occurred_at >= from` (alias `from_dt`) |
| `to` | ISO-8601 | – | `occurred_at <= to` |

The `q` filter and the structured filters **compose**: `q` is
ANDed with every other clause. Naive ISO date strings (no
timezone) are stamped as UTC.

### Detail response (`/audit-log/{id}`)

```jsonc
{
  "data": {
    "id": 4521,
    "occurred_at": "2026-05-03T14:21:08Z",
    "action": "collection.published",
    "actor_id": "8c2b…",
    "actor_username": "anna",
    "target_type": "collection",
    "target_id": "manzoni",
    "target_label": "Manzoni",
    "payload": { "note": "release 1.2", "content_changed": true },
    "user_agent": "Mozilla/5.0 …"
  }
}
```

`ip_address` is **deliberately not exposed** to the API even for
Admins — the production logger middleware hashes the IP with the
`JWT_SECRET` salt before it ever reaches the table, and surfacing
the hash adds nothing useful in the UI while paying a privacy cost.

### CSV export

```
GET /audit-log/export.csv?<same filters as list>
```

Streams `text/csv` in 500-row chunks via keyset pagination on
`audit_log.id` so a multi-million-row export never loads the full
table into memory before the first byte reaches the client.
Columns:

```
id, occurred_at, action, actor_username, target_type, target_id, target_label
```

---

## Frontend

| Path | Role |
|---|---|
| [`frontend/src/stores/auditLog.ts`](../../frontend/src/stores/auditLog.ts) | Pinia store — entries, filters, detail panel, CSV URL builder |
| [`frontend/src/views/admin/AuditLogView.vue`](../../frontend/src/views/admin/AuditLogView.vue) | Filter bar (free-text + 5 structured) + paginated table + JSONB side panel |

### Layout

- **Filter bar**: free-text `q` input across the top, then 5 structured
  controls (`action` dropdown from the curated list,
  `actor_username` substring, `target_type` substring, `from` and
  `to` datetime-locals). Apply / Clear / row counter.
- **Table**: 4 columns (`occurred_at`, `action` badge,
  `actor_username`, `target_type/target_label`). Click a row →
  side panel.
- **Side panel**: `id`, `action`, `actor`, `target`, `user_agent`,
  and the JSONB `payload` rendered as pretty-printed `<pre>`
  (per Q2 decision: simple wins over a tree widget).

The view is wired into the admin sidebar under "Amministra" via
`labelKey: nav.audit_log`.

---

## Integration with the rest of the platform

The audit-log view is **read-only**. Other surfaces continue to
write rows directly via `db.add(AuditLog(...))` — there is no
service-layer gateway. This was a deliberate choice: every action
already has its own service-layer code path, and forcing it
through a single audit gateway would either be a no-op wrapper or
a leaky abstraction.

The fixity layer is the one new contributor — every first
`ok → drifted | missing` transition writes a `fixity.drift_detected`
row, which surfaces in this view alongside the regular workflow
events (per [FIXITY.md](FIXITY.md)).

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/tests/test_audit_log_admin.py`](../../backend/app/tests/test_audit_log_admin.py) | 9 endpoint tests — newest-first ordering, q-OR semantics, structured filters, q+structured composition, curated vocabulary, CSV header, role gating across all four endpoints, payload detail |

---

## Out of scope (deferred per M2 decisions)

- **Real-time tail mode** (auto-poll every N seconds): Q3 — defer.
  Useful during incidents but adds no value in steady state; ship
  when an admin actually asks.
- **Signed JSON Lines export**: Q4 — defer. Some institutional
  audits ask for it; defer until it's the unblocker on a real
  review.
- **Full-text GIN index on `target_label` + `payload`**: spec
  flagged it; deferred until row counts and search habits justify
  the index cost.
