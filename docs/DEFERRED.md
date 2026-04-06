# Deferred Implementations

Items that are architecturally sound but deliberately postponed.
Each entry explains **why** it is deferred and **what trigger** should
prompt revisiting it.

---

## 1. Async task queue (Celery / ARQ / Dramatiq)

**Why deferred**
The current stack has no message broker. Adding one (Redis + Celery worker)
doubles the number of services in docker-compose and introduces a new failure
mode. The first phases do not yet have operations that exceed ~1 s.

**What needs it**
- TEI schema validation at save time (can be slow on large documents)
- XSLT transformation on batch of documents
- Full collection export as ZIP
- Any operation triggered by a publication-state change that touches
  more than a handful of documents

**Trigger to implement**
First user-facing operation that blocks a request for more than 3 seconds,
or the first publication workflow endpoint.

**Preferred stack when the time comes**
ARQ (async-native, uses Redis, no Celery overhead) or Celery with Redis
broker. Worker runs as a separate Docker service. Task status tracked in
a `background_tasks` table (id, status, result, created_at, completed_at).

---

## 2. Plugin hot-reload (activate/deactivate without restart)

**Why deferred**
FastAPI does not support removing mounted routers at runtime. Implementing
hot-reload requires either: (a) a custom router that checks plugin status
on every request, or (b) a subprocess/worker model. Both add significant
complexity with no current use case — all plugins are currently native.

**Trigger to implement**
First non-native plugin that needs to be toggled in production without
a maintenance window.

---

## 3. Plugin data table

**Why deferred**
Non-native plugins with structured relational data need a place to store it
without owning Alembic migrations. A generic `plugin_data` table
`(plugin_id, entity_type, entity_id, data JSONB)` would serve this, but
no non-native plugin exists yet to justify it.

**Trigger to implement**
First non-native plugin that needs more than `system_settings` key-value pairs.

---

## 4. Collection ACL — multi-editor support

**Why deferred**
The current model uses a single `editor_id` on the `collections` table.
If future requirements call for multiple simultaneous editors on one
collection, a `collection_collaborators` table will be needed.

**Trigger to implement**
First explicit request for collaborative editing on a single collection.

---

## 5. TEI schema validation

**Why deferred**
Validating an XML document against TEI P5 requires loading the RelaxNG/XSD
schema (several MB), which is slow unless cached. Synchronous validation
at save time would block the HTTP worker for potentially > 5 s on large
documents. Needs the async task queue (item 1) as a prerequisite.

**Design note**
Use `lxml` (not `defusedxml` — defusedxml explicitly disables schema
validation). Validation runs in a background task; the document is saved
immediately with `validation_status = "pending"`, updated to `"valid"` or
`"invalid"` when the task completes. The user receives a notification
(via the existing notification system) on completion.

**Trigger to implement**
After the async task queue is in place and the document CRUD exists.

---

## 6. XSLT template management (Designer role)

**Why deferred**
The Designer role is defined in ACL but has no dedicated endpoints.
Managing XSLT templates requires: storage (filesystem or eXist-db),
versioning, and a frontend editor. It is a self-contained feature that
depends on the XML layer being in place first.

**Trigger to implement**
Phase 05+ — after document CRUD and collection management.

---

## 7. Document versioning

**Why deferred**
eXist-db has built-in versioning (versioning module), but enabling it
requires per-collection configuration. Whether to use eXist-db versioning
or a manual snapshot table in PostgreSQL is an open architectural decision.

**Open question**
- eXist-db versioning: automatic, no extra code, but opaque and hard to
  expose via API.
- PostgreSQL snapshot table: full control, queryable diff history, but
  requires storing XML blobs or diffs.

**Trigger to implement**
Phase 05+ — decide the approach when document CRUD is designed.

---

## 8. Full-text search across collections

**Why deferred**
eXist-db has native XQuery full-text search (KWIC, Lucene index).
PostgreSQL has `pg_trgm` (already installed) for user/metadata search.
Cross-layer search (metadata + document content in one query) requires
a coordination layer that does not yet have a use case.

**Trigger to implement**
When the first "search documents by content" endpoint is requested.

---

## 9. WebSocket / Server-Sent Events for real-time notifications

**Why deferred**
The current notification system is pull-based (frontend calls
`/notifications/unread-count` at boot). Real-time push requires either
WebSockets or SSE, both of which need connection state management and
are incompatible with simple horizontal scaling behind a load balancer
without a shared pub/sub layer (Redis).

**Trigger to implement**
When polling latency becomes a visible UX problem, or when the async
task queue (item 1) is in place and can publish events to a Redis channel.

---

## 10. Production hardening checklist

Items that must be completed before any public-facing deployment but are
out of scope during development phases:

| Item | Status | Notes |
|------|--------|-------|
| HTTPS enforcement | deferred | Uncomment HSTS header in nginx.conf |
| Content-Security-Policy | deferred | Header template exists in nginx.conf |
| Rate limit tuning | deferred | Current limits are defaults |
| `bcrypt_rounds` review | deferred | Default 12; increase to 14 for production |
| `ADMIN_PASSWORD` rotation policy | deferred | Document in ops runbook |
| Postgres connection pooling | deferred | Consider PgBouncer under load |
| eXist-db admin password rotation | deferred | Same var as backend — enforce secret manager |
| Log shipping | deferred | structlog JSON → ELK / Loki in production |
| Backup strategy | deferred | PostgreSQL dump + eXist-db backup API |

---

## 11. Email / external notification channels

**Why deferred**
The `notification_dispatcher` plugin currently writes only in-app
notifications. Email delivery requires an SMTP integration (or SES/Postmark)
and an email template system (HTML + plaintext). No email use case exists yet.

**Trigger to implement**
First user-facing flow that requires out-of-band notification:
password reset, publication approval, or account verification.

---

*Last updated: 2026-04-06*
