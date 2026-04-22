# Plugin Architecture — Technical Reference

This document describes the Aracne2 plugin system: how plugins are discovered,
loaded, and mounted at startup; how the hook event bus works; the catalogue of
built-in native plugins; and, in the appendix, a step-by-step guide for
building a non-native (user-installed) plugin.

---

## Table of contents

1. [Concepts and vocabulary](#1-concepts-and-vocabulary)
2. [Directory layout](#2-directory-layout)
3. [Core components](#3-core-components)
   - [PluginMeta](#31-pluginmeta)
   - [PluginBase](#32-pluginbase)
   - [PluginLoader](#33-pluginloader)
   - [HookRegistry and HookEvent](#34-hookregistry-and-hookevent)
   - [Plugin ORM model](#35-plugin-orm-model)
4. [Startup sequence](#4-startup-sequence)
5. [Hook event reference](#5-hook-event-reference)
6. [Native plugins catalogue](#6-native-plugins-catalogue)
   - [ai](#61-ai--ai-integration)
   - [audit_logger](#62-audit_logger--audit-logging)
   - [collections](#63-collections--collections-management)
   - [evt](#64-evt--evt-viewer-integration)
   - [named_entities](#65-named_entities--named-entity-index)
   - [notification_dispatcher](#66-notification_dispatcher--in-app-notifications)
   - [oai_pmh](#67-oai_pmh--oai-pmh-provider)
   - [webhook_dispatcher](#68-webhook_dispatcher--webhook-notifications)
7. [Native vs. non-native](#7-native-vs-non-native)
8. [Appendix — Building a non-native plugin](#appendix--building-a-non-native-plugin)

---

## 1. Concepts and vocabulary

| Term | Meaning |
|------|---------|
| **Plugin** | A self-contained Python package in `backend/app/plugins/` that adds routes, listens to events, or both |
| **Native plugin** | Ships with Aracne2; always active; cannot be deactivated; located in `plugins/_native/` |
| **Non-native plugin** | User-installed; starts inactive; toggled by Admin; located in `plugins/<slug>/` |
| **PluginMeta** | Frozen dataclass carrying a plugin's identity metadata |
| **PluginLoader** | Singleton that discovers, syncs, and mounts all plugins at startup |
| **HookRegistry** | Async event bus; plugins register handlers, services emit events |
| **HookEvent** | String constants identifying lifecycle events (`"user.created"`, etc.) |
| **Plugin row** | PostgreSQL row in the `plugins` table tracking status and metadata |

---

## 2. Directory layout

```
backend/app/plugins/
├── _native/                   ← always loaded; meta.native = True
│   ├── ai/
│   │   ├── plugin.py
│   │   ├── router.py
│   │   ├── service.py
│   │   └── providers/
│   ├── audit_logger/
│   │   └── plugin.py
│   ├── collections/
│   │   ├── plugin.py
│   │   └── router.py
│   ├── evt/
│   │   ├── plugin.py
│   │   ├── router.py
│   │   └── service.py
│   ├── named_entities/
│   │   ├── plugin.py
│   │   ├── router.py
│   │   ├── service.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── notification_dispatcher/
│   │   └── plugin.py
│   ├── oai_pmh/
│   │   ├── plugin.py
│   │   ├── router.py
│   │   └── service.py
│   └── webhook_dispatcher/
│       ├── plugin.py
│       ├── router.py
│       ├── service.py
│       ├── models.py
│       └── schemas.py
│
└── <user_slug>/               ← user-installed; meta.native = False
    └── plugin.py              ← minimum required file
```

The loader scans directories alphabetically and skips any entry whose name
starts with `_` (underscore), so `_native/` itself, `__init__.py`, and any
private helper packages are never treated as plugin roots.

---

## 3. Core components

### 3.1 PluginMeta

**File**: `backend/app/core/plugin_base.py`

An immutable frozen dataclass that every plugin declares as a class variable.
The `id` field must match the plugin's directory name exactly.

```python
@dataclass(frozen=True)
class PluginMeta:
    id: str          # Unique slug; must equal the folder name (snake_case)
    name: str        # Human-readable name shown in the Admin UI
    version: str     # Semver string, e.g. "1.0.0"
    native: bool     # True = always active, cannot be deactivated
    description: str # Short description shown in the Admin UI
    author: str      = "Aracne2 Team"
    min_role: str    = "Admin"   # Minimum role to interact with plugin UI
```

The loader enforces that `meta.native` matches the directory the plugin lives
in (`_native/` → `True`; top-level → `False`). A mismatch is logged as a
warning and the plugin is still loaded with the declared value.

---

### 3.2 PluginBase

**File**: `backend/app/core/plugin_base.py`

Abstract base class. Every plugin defines a single class named `Plugin` that
inherits from it.

```python
class PluginBase(ABC):
    meta:   ClassVar[PluginMeta]  # Must be set
    router: ClassVar[APIRouter]   # Must be set (empty APIRouter() if no routes)

    @classmethod
    def on_activate(cls) -> None:
        """Called once when an Admin activates this plugin.
        Never called for native plugins. Default implementation is a no-op."""

    @classmethod
    def on_deactivate(cls) -> None:
        """Called once when an Admin deactivates this plugin.
        Never called for native plugins. Default implementation is a no-op."""
```

**Rules:**

- The class must be named `Plugin` (the loader inspects all classes in the
  module and picks the first `PluginBase` subclass)
- `meta` and `router` are `ClassVar` — they belong to the class, not instances
- If the plugin has no HTTP routes, set `router = APIRouter()` (empty)
- Hook handlers are registered at **module level**, outside the class, so they
  fire even before the class is fully resolved

---

### 3.3 PluginLoader

**File**: `backend/app/core/plugin_loader.py`

A singleton (`plugin_loader`) that runs the full plugin lifecycle during
FastAPI startup. It never runs again after boot.

#### `discover()`

Scans the filesystem for `plugin.py` files:

1. `plugins/_native/<slug>/plugin.py` — native plugins
2. `plugins/<slug>/plugin.py` — user-installed plugins

For each file found, the loader imports the module with `importlib.import_module`
and uses `inspect.getmembers` to find the `PluginBase` subclass. The class is
stored in `_discovered[meta.id]`.

Errors during import are logged and the plugin is skipped; the platform
continues to start.

#### `sync_registry(db)`

Upserts a row in the `plugins` PostgreSQL table for every discovered plugin:

- **New plugin**: inserts with `status = active` (native) or
  `status = inactive` (non-native)
- **Existing plugin**: updates `display_name`, `version`, `description`,
  `author`, `entry_point`, `updated_at`; forces `status = active` for native
  plugins (Admin cannot deactivate them)

The `entry_point` field is set to the Python import path:
`app.plugins._native.<slug>.plugin` or `app.plugins.<slug>.plugin`.

#### `load_active(app, db)`

Calls `discover()` then `sync_registry()`, then for each discovered plugin
where the DB row has `status = active`:

```python
if cls.router.routes:                        # skip empty routers
    app.include_router(cls.router, prefix="/api/v1")
```

All routes from all active plugins are mounted under the `/api/v1` prefix.
Each plugin's `APIRouter` must define its own sub-prefix (e.g.
`APIRouter(prefix="/webhooks")`).

#### `get_class(plugin_id)`

Returns the `PluginBase` subclass for a given plugin id, or `None`. Used by
the Admin endpoints that call `on_activate` / `on_deactivate`.

---

### 3.4 HookRegistry and HookEvent

**File**: `backend/app/core/hooks.py`

A lightweight async event bus. It has no dependencies on FastAPI or SQLAlchemy.

```python
hook_registry = HookRegistry()   # module-level singleton
```

#### Registering a handler

```python
# At module level in plugin.py — runs at import time
hook_registry.register(HookEvent.ON_USER_CREATED, my_handler)
```

Handlers are called in registration order. Multiple plugins can register for
the same event.

#### Emitting an event

Emitted by core services (never by plugins directly):

```python
await hook_registry.emit(HookEvent.ON_USER_CREATED, db=db, actor=actor, user=user)
```

All keyword arguments passed to `emit()` are forwarded to every registered
handler unchanged.

#### Error isolation

```python
async def emit(self, event: str, **kwargs: Any) -> None:
    for handler in self._handlers.get(event, []):
        try:
            await handler(**kwargs)
        except Exception as exc:
            logger.error("hook_handler_error", event=event,
                         handler=handler.__name__, error=str(exc))
    # emit() always returns — one failing handler never blocks the others
```

A handler that raises an exception is logged and skipped; all subsequent
handlers still run; the calling service is never affected.

---

### 3.5 Plugin ORM model

**File**: `backend/app/models/plugin.py`
**Table**: `plugins`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `UUID` PK | Auto-generated |
| `name` | `VARCHAR(128)` UNIQUE | Plugin slug (equals `meta.id`) |
| `display_name` | `VARCHAR(256)` | From `meta.name` |
| `version` | `VARCHAR(32)` | From `meta.version` |
| `description` | `TEXT` | From `meta.description` |
| `author` | `VARCHAR(256)` | From `meta.author` |
| `entry_point` | `TEXT` | Python import path |
| `status` | `PluginStatus` enum | `active`, `inactive`, `error` |
| `config` | `JSONB` | Plugin-specific config (default `{}`) |
| `hooks` | `JSONB` | List of registered event names (informational) |
| `installed_at` | `DATETIME(tz)` | First discovery timestamp |
| `updated_at` | `DATETIME(tz)` | Last metadata sync timestamp |
| `is_native` | `bool` | True if in `_native/` |
| `installed_by` | `UUID FK → users.id` | SET NULL on delete; null for native |

The `config` JSONB column is available for plugins that need per-installation
configuration (e.g. custom API endpoints, feature flags). It is not used by any
native plugin but is reserved for non-native plugins.

---

## 4. Startup sequence

The complete sequence runs once, inside the FastAPI
[lifespan](https://fastapi.tiangolo.com/advanced/events/) context manager in
`backend/app/main.py`:

```
FastAPI boot
  │
  ├─ Connect to eXist-db
  ├─ Verify PostgreSQL connectivity
  ├─ Seed licenses, body templates, AI prompts (idempotent)
  │
  ├─ plugin_loader.load_active(app, db)
  │     ├─ discover()
  │     │     ├─ scan plugins/_native/*/plugin.py  → _discovered (native)
  │     │     └─ scan plugins/*/plugin.py          → _discovered (non-native)
  │     │
  │     ├─ sync_registry(db)
  │     │     └─ upsert Plugin row for each _discovered entry
  │     │           • native  → status forced to "active"
  │     │           • new non-native → status = "inactive"
  │     │
  │     └─ for each Plugin where status = "active":
  │           └─ app.include_router(cls.router, prefix="/api/v1")
  │
  ├─ Ensure filesystem directories (websites_root, media_dir)
  └─ Start APScheduler (purge jobs, etc.)
  
  ↓  yield — app is now serving requests
  
  ├─ APScheduler.shutdown()
  └─ Close eXist-db + PostgreSQL connections
```

**Import-time side effects**: hook registrations in `plugin.py` files run
during `discover()` → `importlib.import_module()`. By the time routes are
mounted, all handlers are already registered in `hook_registry`.

---

## 5. Hook event reference

All constants are defined in `app/core/hooks.py` as class attributes of
`HookEvent`.

### User lifecycle

| Constant | Value | Emitted by | kwargs |
|----------|-------|-----------|--------|
| `ON_USER_LOGIN` | `"user.login"` | `routers/auth.py` | `db`, `user` |
| `ON_USER_LOGOUT` | `"user.logout"` | `routers/auth.py` | `db`, `user` |
| `ON_USER_CREATED` | `"user.created"` | `services/users.py` | `db`, `actor`, `user` |
| `ON_USER_UPDATED` | `"user.updated"` | `services/users.py` | `db`, `actor`, `user`, `changes` |
| `ON_USER_DELETED` | `"user.deleted"` | `services/users.py` | `db`, `actor`, `user` |

### Plugin lifecycle

| Constant | Value | Emitted by | kwargs |
|----------|-------|-----------|--------|
| `ON_PLUGIN_ACTIVATED` | `"plugin.activated"` | `routers/plugins.py` | `plugin_id` |
| `ON_PLUGIN_DEACTIVATED` | `"plugin.deactivated"` | `routers/plugins.py` | `plugin_id` |

### Collection lifecycle

| Constant | Value | Emitted by | kwargs |
|----------|-------|-----------|--------|
| `ON_COLLECTION_SUBMITTED` | `"collection.submitted"` | `services/xmldb.py` | `collection` |
| `ON_COLLECTION_PUBLISHED` | `"collection.published"` | `services/xmldb.py` | `collection` |
| `ON_COLLECTION_UNPUBLISHED` | `"collection.unpublished"` | `services/xmldb.py` | `collection` |

### Document lifecycle

| Constant | Value | Emitted by | kwargs |
|----------|-------|-----------|--------|
| `ON_DOCUMENT_UPLOADED` | `"document.uploaded"` | `services/xmldb.py` | `collection`, `filename` |
| `ON_DOCUMENT_DELETED` | `"document.deleted"` | `services/xmldb.py` | `collection`, `filename` |

**Handler signature convention**: handlers should accept `**kwargs` for
forward compatibility. Access specific arguments with `cast()` or `.get()`:

```python
async def _on_user_created(**kwargs: object) -> None:
    from app.models.user import User
    from typing import cast
    db = cast(AsyncSession | None, kwargs.get("db"))
    user = cast(User | None, kwargs.get("user"))
    if db is None or user is None:
        return
    # ... handler logic
```

---

## 6. Native plugins catalogue

### 6.1 `ai` — AI Integration

| | |
|---|---|
| **Location** | `plugins/_native/ai/` |
| **Routes** | Yes — prefix `/ai` |
| **Hooks** | None |
| **min_role** | Editor |

Provides LLM-assisted workflows across the platform. Supports four providers
(OpenAI, Anthropic, Google Gemini, Ollama) selectable via the `ai_provider`
system setting. Ollama runs locally — no API key, no data leaves the server
— and is bundled as an optional Docker Compose service under profile
`ai-local`. All AI requests are streamed via Server-Sent Events (SSE).

Optional retrieval-augmented generation (RAG) layer — when
`ai_rag_enabled=true` and the pgvector service is configured, prompts
whose template contains `{rag_context}` receive top-matching passages
from a semantic index injected before reaching the LLM. The ingestion
pipeline (`python -m app.scripts.ingest_tei_p5`) turns a directory of
HTML / XML / Markdown / plain-text files into embedded chunks. Fail-soft
at every step: with RAG off or the index empty, `{rag_context}` resolves
to an empty string and the base prompt still reaches the provider.

**Seeded native prompts** (`is_native=true`, editable but not deletable):

- `validate_errors_explain` — analyse validation errors (validation panel)
- `document_edit_suggest` — improve a TEI selection (editor)
- `document_discuss` — free multi-turn chat on a selection (editor)
- `tei_bibl_inline` — free-text citation → `<biblStruct>` (editor, RAG-aware)
- `tei_extract_entities` — wrap `<persName>/<placeName>/<orgName>` in a passage (editor, RAG-aware)
- `tei_header_scaffold` — scaffold `<teiHeader>` from metadata (editor, RAG-aware)
- `xslt_debug`, `xslt_discuss` — XSLT error analysis and free chat (WebsiteEditView)
- `bibliobuilder` — bulk `<listBibl>` normalisation (dedicated view)

**Endpoints:**

| Method | Path | ACL | Description |
|--------|------|-----|-------------|
| `GET` | `/api/v1/ai/prompts` | Editor+ | List all prompt templates |
| `POST` | `/api/v1/ai/prompts` | Admin | Create custom prompt |
| `PATCH` | `/api/v1/ai/prompts/{slug}` | Admin | Update prompt |
| `DELETE` | `/api/v1/ai/prompts/{slug}` | Admin | Delete custom prompt |
| `GET` | `/api/v1/ai/config` | Auth | Get active provider, model, rate limit |
| `POST` | `/api/v1/ai/complete` | Editor+ | Stream completion (SSE) |

See [AI_INTEGRATION.md](AI_INTEGRATION.md) for the full AI subsystem
reference including the RAG architecture, provider adapters (Ollama
NDJSON included) and the 9 native prompt templates. See
[OPERATIONS.md](../OPERATIONS.md) § "Local AI" for the operator-facing
runbook (enabling the profile, pulling models, ingesting TEI P5,
switching models).

---

### 6.2 `audit_logger` — Audit Logging

| | |
|---|---|
| **Location** | `plugins/_native/audit_logger/` |
| **Routes** | None |
| **Hooks** | `user.created`, `user.updated`, `user.deleted` |
| **min_role** | Admin |

Records sensitive platform actions to the `audit_log` table. Operates entirely
through hooks — has no HTTP endpoints. Cannot be deactivated.

Current handler implementations are stubs reserved for future population of the
`audit_log` table.

---

### 6.3 `collections` — Collections Management

| | |
|---|---|
| **Location** | `plugins/_native/collections/` |
| **Routes** | Yes — prefix `/collections` |
| **Hooks** | None (emits events; does not listen) |
| **min_role** | Editor |

The largest native plugin (~43 endpoints). Implements the entire collection and
document lifecycle: CRUD, editorial workflow (draft → assigned → review →
published), document upload/download, schema validation, bibliography
management, and ACL permission grants.

The service layer in this plugin emits `ON_COLLECTION_SUBMITTED`,
`ON_COLLECTION_PUBLISHED`, `ON_COLLECTION_UNPUBLISHED`,
`ON_DOCUMENT_UPLOADED`, and `ON_DOCUMENT_DELETED`.

See [COLLECTIONS.md](COLLECTIONS.md) for the full reference.

---

### 6.4 `evt` — EVT Viewer Integration

| | |
|---|---|
| **Location** | `plugins/_native/evt/` |
| **Routes** | Yes — prefix `/public` |
| **Hooks** | None |
| **min_role** | User |

Exposes two public, cacheable endpoints that feed the EVT 2 viewer:

| Method | Path | Cache | Description |
|--------|------|-------|-------------|
| `GET` | `/api/v1/public/collections/{slug}/evt-config` | 60 s | EVT 2 `config.json` |
| `GET` | `/api/v1/public/collections/{slug}/documents/{filename}/raw` | 300 s | Raw XML |

Both endpoints are designed to be proxied by nginx. The EVT viewer UI is
deployed separately via a Docker Compose profile.

---

### 6.5 `named_entities` — Named Entity Index

| | |
|---|---|
| **Location** | `plugins/_native/named_entities/` |
| **Routes** | Yes — prefixes `/entities` |
| **Hooks** | `document.uploaded`, `document.deleted` |
| **min_role** | Admin |

Automatically indexes `<persName>`, `<placeName>`, and `<orgName>` elements
from TEI documents using an XQuery script. Indexing is triggered by document
lifecycle hooks and runs as a background `asyncio.create_task`. Admin endpoints
allow canonical form editing, authority linking, entity merging, and manual
re-indexing.

**Endpoints (partial):**

| Method | Path | ACL | Description |
|--------|------|-----|-------------|
| `GET` | `/api/v1/entities` | Public | Named entities from public collections |
| `GET` | `/api/v1/entities/{id}/occurrences` | Public | Occurrences of one entity |
| `GET` | `/api/v1/entities/admin` | Admin | All entities (all collections) |
| `PUT` | `/api/v1/entities/admin/{id}` | Admin | Update canonical form / authority ref |
| `POST` | `/api/v1/entities/admin/merge` | Admin | Merge two entities |
| `POST` | `/api/v1/entities/admin/reindex/{slug}` | Admin | Full collection re-index |

---

### 6.6 `notification_dispatcher` — In-App Notifications

| | |
|---|---|
| **Location** | `plugins/_native/notification_dispatcher/` |
| **Routes** | None |
| **Hooks** | `user.created` |
| **min_role** | Admin |

Writes `Notification` rows on user lifecycle events. Currently sends a welcome
notification on account creation, localized to the user's `preferred_lang`
(`"it"` or `"en"`). Designed as a model for hook-only plugins: minimal,
side-effect-driven, no HTTP layer.

```python
# Full plugin.py (minus imports):
async def _on_user_created(**kwargs: object) -> None:
    db   = cast(AsyncSession | None, kwargs.get("db"))
    user = cast(User | None, kwargs.get("user"))
    if db is None or user is None:
        return
    lang = getattr(user, "preferred_lang", "en") or "en"
    db.add(Notification(
        user_id=user.id,
        type="welcome",
        title=_WELCOME_TITLE.get(lang, _WELCOME_TITLE["en"]),
        body=_WELCOME_BODY.get(lang,  _WELCOME_BODY["en"]),
    ))

hook_registry.register(HookEvent.ON_USER_CREATED, _on_user_created)

class Plugin(PluginBase):
    meta   = PluginMeta(id="notification_dispatcher", native=True, ...)
    router = APIRouter()   # no routes
```

---

### 6.7 `oai_pmh` — OAI-PMH Provider

| | |
|---|---|
| **Location** | `plugins/_native/oai_pmh/` |
| **Routes** | Yes — prefix `/oai` |
| **Hooks** | None |
| **min_role** | Admin |

Makes published public collections harvestable by metadata aggregators
(DART, OpenDOAR, Europeana, etc.) via the OAI-PMH 2.0 protocol. Each
collection maps to an OAI-PMH set; each XML document maps to a record with
Dublin Core metadata extracted from the TEI header.

Single endpoint: `GET /api/v1/oai?verb=<VERB>&…`

Supported verbs: `Identify`, `ListSets`, `ListMetadataFormats`,
`ListIdentifiers`, `ListRecords`, `GetRecord`.

Only `oai_dc` (Dublin Core) metadata format is supported.

---

### 6.8 `webhook_dispatcher` — Webhook Notifications

| | |
|---|---|
| **Location** | `plugins/_native/webhook_dispatcher/` |
| **Routes** | Yes — prefix `/webhooks` |
| **Hooks** | `collection.submitted`, `collection.published`, `collection.unpublished`, `document.uploaded`, `document.deleted` |
| **min_role** | Admin |

Delivers HTTP POST payloads to external URLs on collection and document events.
Features:
- Per-endpoint event subscription (subscribe to one or more events)
- Optional HMAC-SHA256 request signing (`X-Aracne2-Signature` header)
- Automatic retries: up to 3 attempts with exponential backoff
- Per-endpoint status tracking: `last_triggered_at`, `last_status_code`,
  `last_error`
- Test ping endpoint: `POST /api/v1/webhooks/{id}/test`

**Payload structure:**

```json
{
  "event": "collection.published",
  "collection_id": "uuid",
  "slug": "dante",
  "title": "Divina Commedia",
  "is_public": true,
  "doc_count": 3,
  "status": "published",
  "published_at": "2026-04-15T10:00:00+00:00",
  "filename": "inferno.xml"   // present only for document events
}
```

---

## 6b. Bundled non-native plugins

Plugins that ship with the repo under `plugins/<slug>/` (no underscore prefix).
They are discovered on every startup but start as **inactive** — an Admin must
activate them from `/admin/plugins`.

### 6b.1 `zenodo_deposit` — Zenodo Deposit

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
- Per-collection deposit record stored in `plugin_data` (deposit id, DOI,
  record URL, status, submitted_at). Re-deposit is idempotent on failures
  and skipped on already-successful deposits unless forced.
- Metadata is built by the plugin's own `mapping.py` module via a reusable
  `DepositMetadata` intermediate — so a future DataCite or HAL plugin can
  plug in a different serialiser without re-extracting from the ORM.
- License vocabulary id mapped from the seeded Creative Commons licenses
  (`cc-by-4.0`, `cc-by-sa-4.0`, `cc0-1.0`, …).

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
  vocabulary ids) and `zenodo_access_right` → `zenodo_access` (folding
  `embargoed`/`closed` into `restricted`).

**Frontend:**
- Dedicated config page at `/admin/plugins/zenodo_deposit/config` (reached
  via the "Configure" link in the plugins list).
- A deposit badge next to the status pill in `/collections/:slug`, with a
  "Re-deposit on Zenodo" button for EditorInChief and above.

---

## 7. Native vs. non-native

| Aspect | Native | Non-native |
|--------|--------|-----------|
| Directory | `plugins/_native/<slug>/` | `plugins/<slug>/` |
| `meta.native` | `True` | `False` |
| Initial DB status | `active` | `inactive` |
| Can Admin deactivate? | No | Yes |
| On status change | — | `on_activate()` / `on_deactivate()` called |
| Takes effect | Always at boot | After next restart |
| Can Admin delete? | No | Yes (remove directory + restart) |
| `installed_by` | `null` | UUID of the Admin who installed it |

Non-native plugins start as `inactive` even after the directory is dropped into
place. An Admin must activate them via the admin panel. The activation triggers
a call to `on_activate()` and sets the DB row to `active`. The routes are only
mounted after the next server restart (because `include_router` can only be
called during the lifespan startup).

---

## Appendix — Building a non-native plugin

This appendix is a complete step-by-step guide for creating a user-installed
plugin that:

- Adds two HTTP endpoints
- Listens to a hook event
- Persists its own data in PostgreSQL
- Has an Alembic migration

The example plugin is a simple **"document changelog"**: every time a document
is uploaded, it appends a row to a `changelog` table. A public read endpoint
lists the recent changelog entries for a collection.

---

### A.1 File structure

```
backend/app/plugins/doc_changelog/
├── __init__.py          (empty)
├── plugin.py            (required — loader entry point)
├── router.py            (HTTP endpoints)
├── service.py           (business logic)
├── models.py            (SQLAlchemy ORM)
└── schemas.py           (Pydantic v2 schemas)
```

Only `plugin.py` is strictly required. Add the other files as needed.

---

### A.2 ORM model (`models.py`)

```python
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ChangelogEntry(Base):
    __tablename__ = "doc_changelog"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_slug: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
```

---

### A.3 Alembic migration

Create a new migration file in `backend/alembic/versions/`:

```
alembic revision --autogenerate -m "add doc_changelog table"
```

Edit the generated file — confirm `upgrade()` and implement `downgrade()`:

```python
def upgrade() -> None:
    op.create_table(
        "doc_changelog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("collection_slug", sa.String(256), nullable=False, index=True),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("doc_changelog")
```

Run the migration:

```bash
docker compose exec backend alembic upgrade head
```

---

### A.4 Pydantic schema (`schemas.py`)

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChangelogEntryResponse(BaseModel):
    id: UUID
    collection_slug: str
    filename: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### A.5 Service (`service.py`)

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.plugins.doc_changelog.models import ChangelogEntry
from app.plugins.doc_changelog.schemas import ChangelogEntryResponse


async def append_entry(db: AsyncSession, slug: str, filename: str) -> None:
    db.add(ChangelogEntry(collection_slug=slug, filename=filename))
    # No flush needed here — the hook handler's caller commits the session.


async def list_entries(
    db: AsyncSession, slug: str, limit: int = 50
) -> list[ChangelogEntryResponse]:
    rows = await db.scalars(
        select(ChangelogEntry)
        .where(ChangelogEntry.collection_slug == slug)
        .order_by(ChangelogEntry.created_at.desc())
        .limit(limit)
    )
    return [ChangelogEntryResponse.model_validate(r) for r in rows]
```

---

### A.6 Router (`router.py`)

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_async_session
from app.middleware.acl import require_role
from app.plugins.doc_changelog.schemas import ChangelogEntryResponse
from app.plugins.doc_changelog.service import list_entries

router = APIRouter(prefix="/changelog", tags=["changelog"])

_auth = Depends(require_role(min_role="User"))


@router.get("/{slug}", dependencies=[_auth])
async def get_changelog(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[ChangelogEntryResponse]:
    """Return the 50 most recent changelog entries for a collection."""
    return await list_entries(db, slug)
```

Final route: `GET /api/v1/changelog/{slug}`

---

### A.7 Plugin entry point (`plugin.py`)

```python
"""
Doc Changelog — non-native plugin.

Appends a row to doc_changelog on every document upload.
Exposes a read endpoint at GET /api/v1/changelog/{slug}.
"""

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hooks import HookEvent, hook_registry
from app.core.plugin_base import PluginBase, PluginMeta
from app.models.collection import Collection
from app.plugins.doc_changelog.router import router


async def _on_document_uploaded(**kwargs: object) -> None:
    # Lazy import to avoid circular imports at module load.
    from app.plugins.doc_changelog.service import append_entry

    db = cast(AsyncSession | None, kwargs.get("db"))
    collection = cast(Collection | None, kwargs.get("collection"))
    filename = cast(str | None, kwargs.get("filename"))
    if db is None or collection is None or filename is None:
        return
    await append_entry(db, collection.slug, filename)


# Register the handler at module level — runs at import time during discover().
hook_registry.register(HookEvent.ON_DOCUMENT_UPLOADED, _on_document_uploaded)


class Plugin(PluginBase):
    meta = PluginMeta(
        id="doc_changelog",      # Must match the directory name exactly
        name="Document Changelog",
        version="1.0.0",
        native=False,            # Non-native: starts inactive
        description="Appends a row to doc_changelog on every document upload.",
        author="Your Name",
        min_role="User",
    )
    router = router
```

---

### A.8 Activating the plugin

1. **Drop the directory** into `backend/app/plugins/doc_changelog/`

2. **Run the migration** so the `doc_changelog` table exists:

   ```bash
   docker compose exec backend alembic upgrade head
   ```

3. **Restart the backend** so `plugin_loader.discover()` picks up the new
   directory and `sync_registry()` inserts the Plugin row as `inactive`:

   ```bash
   docker compose restart backend
   ```

4. **Activate via Admin UI**: Settings → Plugins → doc_changelog → Activate.
   This sets the DB row to `active` and calls `Plugin.on_activate()`.

5. **Restart again** to mount the router:

   ```bash
   docker compose restart backend
   ```

   After this, `GET /api/v1/changelog/{slug}` is live.

> The two-restart pattern (first sync the DB row, then mount the router) is
> a deliberate design: the Admin confirms the plugin before it starts serving
> traffic.

---

### A.9 Deactivating and removing the plugin

**Deactivate** (keeps the directory; stops routes and hooks on next restart):

1. Admin UI → Plugins → doc_changelog → Deactivate → calls `on_deactivate()`
2. Restart backend

**Remove** (full uninstall):

1. Deactivate as above
2. Delete `backend/app/plugins/doc_changelog/`
3. Run a downgrade migration if you want to drop the table:
   ```bash
   docker compose exec backend alembic downgrade <previous_revision>
   ```
4. Restart backend — the Plugin row in PostgreSQL is left as a tombstone with
   `status = inactive`; it can be deleted manually if desired

---

### A.10 Checklist for any non-native plugin

- [ ] Directory name equals `meta.id` (snake_case)
- [ ] `plugin.py` contains exactly one class named `Plugin(PluginBase)`
- [ ] `meta.native = False`
- [ ] `router = APIRouter(prefix="/…")` — even if empty
- [ ] Hook handlers registered at module level, outside the `Plugin` class
- [ ] Handler signature accepts `**kwargs: object` and uses `cast()` or `.get()` to extract args
- [ ] Any new SQLAlchemy models added to `alembic/env.py` target metadata
- [ ] Alembic migration includes `downgrade()` that fully reverts `upgrade()`
- [ ] All values read from `app.config.settings` — never `os.environ`
- [ ] New API keys or secrets added to `SENSITIVE_KEYS` in `app/core/encryption.py` and documented in [SYSTEM_SETTINGS.md](SYSTEM_SETTINGS.md)
- [ ] All user-visible strings use `i18n` keys in both `en.json` and `it.json` (if the plugin adds frontend UI)
- [ ] At least one happy-path test and one error-case test per endpoint
