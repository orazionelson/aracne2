# System Settings — Technical Reference

This document is the authoritative reference for all system settings in
Aracne2. **Every time a new setting is added to `seed.py`, a corresponding
entry must be added here.**

---

## Table of contents

1. [Architecture](#1-architecture)
2. [Data model and storage](#2-data-model-and-storage)
3. [Sensitive settings and encryption](#3-sensitive-settings-and-encryption)
4. [API endpoints](#4-api-endpoints)
5. [Frontend stores](#5-frontend-stores)
6. [Setting reference](#6-setting-reference)
   - [Platform & branding](#61-platform--branding)
   - [Authentication & security](#62-authentication--security)
   - [File uploads](#63-file-uploads)
   - [Search & pagination](#64-search--pagination)
   - [Data retention](#65-data-retention)
   - [Document editor](#66-document-editor)
   - [EVT viewer](#67-evt-viewer)
   - [Website caching](#68-website-caching)
   - [AI integration](#69-ai-integration)
7. [How to add a new setting](#7-how-to-add-a-new-setting)

---

## 1. Architecture

System settings are key-value pairs stored in PostgreSQL. They are seeded once
at startup (`make seed` / `python -m app.db.seed`) and updated at runtime by
Admin users through the admin panel.

Two access patterns exist:

| Pattern | Endpoint | Auth | Used by |
|---------|----------|------|---------|
| **Full settings** | `GET /api/v1/settings` | Admin | Admin settings page |
| **Public UI config** | `GET /api/v1/settings/ui-config` | None | App boot, navbar, public pages |

Settings that are consumed by backend services (upload limits, retention days,
AI provider) are read from the database **at request time** — no restart is
needed after changing them.

Settings that are seeded from environment variables (JWT expiry, bcrypt rounds,
etc.) use the environment value only at first seed. The database copy is
documentation; the runtime code still reads from `app.config.settings`.

---

## 2. Data model and storage

**Table**: `system_settings`
**Model**: `backend/app/models/system_setting.py`

| Column | Type | Notes |
|--------|------|-------|
| `key` | `VARCHAR(256)` PRIMARY KEY | Unique setting identifier |
| `value` | `TEXT` NOT NULL | Stored as string; encrypted if sensitive |
| `type` | `VARCHAR(32)` NOT NULL | Type hint: `string`, `int`, `bool` |
| `description` | `TEXT` nullable | Human-readable description |
| `updated_by` | `UUID FK → users.id` | SET NULL on delete; null = seeded |
| `updated_at` | `DATETIME(tz)` | Timestamp of last change |

All values are stored as strings. The `type` field is used by the API and admin
UI to display the correct input widget and validate user input before writing.

**Bool values** are stored as the literal strings `"true"` or `"false"`. The
service layer rejects any other value.

**Int values** are validated with `int(value)` before writing. Non-numeric
input is rejected with `INVALID_SETTING_VALUE`.

---

## 3. Sensitive settings and encryption

API keys are encrypted at rest using AES (via `app.core.encryption`) with the
`JWT_SECRET` environment variable as the encryption key. They are never
returned in plaintext by the API — the response shows `••••••••` instead.

**Sensitive keys** (defined in `app/core/encryption.py`):

- `ai_openai_api_key`
- `ai_anthropic_api_key`
- `ai_gemini_api_key`

Internal services that need the actual value call
`get_decrypted_setting(db, key)` — this function is not accessible from
routers. Routers always call `get_setting(db, key)`, which applies masking.

When an Admin saves a new API key through the UI, the plaintext is sent over
HTTPS and immediately encrypted before being written to the database.

---

## 4. API endpoints

**Router**: `backend/app/routers/settings.py`
**Service**: `backend/app/services/settings.py`

| Method | Path | ACL | Description |
|--------|------|-----|-------------|
| `GET` | `/api/v1/settings` | Admin | List all settings (sensitive values masked) |
| `GET` | `/api/v1/settings/{key}` | Admin | Get a single setting (masked if sensitive) |
| `PATCH` | `/api/v1/settings/{key}` | Admin | Update a setting; validates type before write |
| `GET` | `/api/v1/settings/ui-config` | Public | Subset of settings needed at boot (see §5) |
| `POST` | `/api/v1/settings/logo` | Admin | Upload a logo image; updates `platform_logo_url` |
| `GET` | `/api/v1/settings/logo/file` | Public | Serve the uploaded logo file |

The `PATCH` endpoint body is `{"value": "<string>"}`. The service resolves the
current `type` and validates before writing. On success it returns a
`SettingResponse` with the updated (and masked if sensitive) value.

---

## 5. Frontend stores

### `useSettingStore` (`frontend/src/stores/settings.ts`)

Used only in authenticated admin views.

```typescript
fetchSettings()                        // GET /api/v1/settings
getSetting(key: string): string | null // reads from local cache
updateSetting(key, value)              // PATCH /api/v1/settings/{key}
uploadLogo(file)                       // POST /api/v1/settings/logo
```

### `useUiConfigStore` (`frontend/src/stores/ui_config.ts`)

Fetched before authentication (in `App.vue` on mount) so that the correct
branding is shown on the login page.

```typescript
fetchUiConfig()   // GET /api/v1/settings/ui-config
```

**Keys exposed**:
`platform_name`, `platform_logo_url`, `navbar_bg_color`, `public_home_enabled`,
`home_show_collections`, `home_show_search`, `evt_enabled`.

---

## 6. Setting reference

### 6.1 Platform & branding

---

#### `platform_name`

| | |
|---|---|
| **Type** | `string` |
| **Default** | Value of `PLATFORM_NAME` env var (falls back to `"Aracne2"`) |
| **Editable** | Yes — Admin |

The display name of the platform. Shown in the browser tab title, navbar, and
email notifications.

**Seeded from**: `settings.platform_name` (env var `PLATFORM_NAME`).

**Consumed by**:
- `get_public_config()` → returned in `UiConfigResponse`
- Frontend: `useUiConfigStore` → `<title>` tag, navbar

---

#### `default_language`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"it"` |
| **Editable** | Yes — Admin |

Default UI language used before a user logs in or if no `preferred_lang` is
set. Valid values: any locale code supported by vue-i18n (`"it"`, `"en"`).

**Consumed by**: not read at runtime in current code — reserved for future
use (e.g. language selector default on login page).

---

#### `platform_logo_url`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"/aracne-logo.png"` |
| **Editable** | Via logo upload (POST /api/v1/settings/logo) |

URL of the logo image displayed in the navbar. Updated automatically when an
Admin uploads a new logo via `POST /api/v1/settings/logo`; the new value is
always `/api/v1/settings/logo/file`.

Accepted upload formats: `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.webp`.

**Consumed by**:
- `get_public_config()` → `UiConfigResponse.platform_logo_url`
- Frontend: `useUiConfigStore` → navbar `<img>` src

---

#### `navbar_bg_color`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"#1e40af"` |
| **Editable** | Yes — Admin |

CSS color string applied to the navbar background. Accepts any valid CSS color
value (`#rrggbb`, `rgb(…)`, named colors, etc.).

**Consumed by**:
- `get_public_config()` → `UiConfigResponse.navbar_bg_color`
- Frontend: `useUiConfigStore` → navbar inline style `:style="{ background: uiConfig.navbar_bg_color }"`

---

#### `public_home_enabled`

| | |
|---|---|
| **Type** | `bool` |
| **Default** | `false` |
| **Editable** | Yes — Admin |

When `false`, the public home page (`/`) is disabled; unauthenticated users
are redirected to the login page. When `true`, the home page is accessible
without authentication and shows the sections configured by
`home_show_collections` and `home_show_search`.

**Consumed by**:
- `get_public_config()` → `UiConfigResponse.public_home_enabled`
- Frontend: `useUiConfigStore` + Vue Router guard → redirect to login

---

#### `home_show_collections`

| | |
|---|---|
| **Type** | `bool` |
| **Default** | `true` |
| **Editable** | Yes — Admin |

Whether the public home page shows the list of published collections.
Only relevant when `public_home_enabled = true`.

**Consumed by**:
- `get_public_config()` → `UiConfigResponse.home_show_collections`
- Frontend: `PublicHomeSection.vue` — conditionally renders the collections panel

---

#### `home_show_search`

| | |
|---|---|
| **Type** | `bool` |
| **Default** | `true` |
| **Editable** | Yes — Admin |

Whether the public home page shows the full-text search bar.
Only relevant when `public_home_enabled = true`.

**Consumed by**:
- `get_public_config()` → `UiConfigResponse.home_show_search`
- Frontend: `PublicHomeSection.vue` — conditionally renders the search panel

---

### 6.2 Authentication & security

> **Note**: the settings in this group are seeded from environment variables
> and serve as an audit record of the current configuration. The backend reads
> these values from `app.config.settings` (env), not from the database, at
> runtime. Changing them in the admin panel has **no effect** without a code
> change and restart.

---

#### `jwt_access_expiry_min`

| | |
|---|---|
| **Type** | `int` |
| **Default** | Value of `JWT_ACCESS_EXPIRY_MINUTES` env var (default: `60`) |
| **Editable** | Yes (no runtime effect — requires env change + restart) |

Lifetime of the JWT access token in minutes.

---

#### `jwt_refresh_expiry_days`

| | |
|---|---|
| **Type** | `int` |
| **Default** | Value of `JWT_REFRESH_EXPIRY_DAYS` env var (default: `30`) |
| **Editable** | Yes (no runtime effect — requires env change + restart) |

Lifetime of the httpOnly refresh cookie in days.

---

#### `public_registration`

| | |
|---|---|
| **Type** | `bool` |
| **Default** | Value of `PUBLIC_REGISTRATION` env var (default: `false`) |
| **Editable** | Yes (no runtime effect — requires env change + restart) |

When `true`, unauthenticated users can register a new account at
`POST /auth/register`. When `false`, only Admin can create accounts.

---

#### `bcrypt_rounds`

| | |
|---|---|
| **Type** | `int` |
| **Default** | Value of `BCRYPT_ROUNDS` env var (default: `12`) |
| **Editable** | Yes (no runtime effect — requires env change + restart) |

Cost factor for bcrypt password hashing. Higher values increase security at the
cost of login latency. Values below 10 are inadvisable in production.

---

### 6.3 File uploads

These settings are read from the database **at request time**, so changes take
effect immediately without a restart.

---

#### `max_upload_size_mb`

| | |
|---|---|
| **Type** | `int` |
| **Default** | Value of `MAX_UPLOAD_SIZE_MB` env var (default: `50`) |
| **Editable** | Yes (no runtime effect — requires env change + restart) |

Maximum size for single-file XML document uploads. Seeded from env; runtime
enforcement currently uses the env value. See also `media_max_upload_size_mb`
for media files.

---

#### `media_max_upload_size_mb`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `50` |
| **Editable** | Yes — Admin (takes effect immediately) |

Maximum size in MB for a single media file upload (images, PDFs, etc.).
Read from the database at each upload request in `_get_max_bytes()` in
`backend/app/routers/media.py`.

---

#### `zip_max_size_mb`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `50` |
| **Editable** | Yes — Admin (takes effect immediately) |

Maximum size in MB for the raw ZIP archive submitted to
`POST /collections/{id}/documents/batch`. Checked before extraction begins.

---

#### `zip_max_extracted_mb`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `200` |
| **Editable** | Yes — Admin (takes effect immediately) |

Maximum total size in MB of all XML files extracted from a ZIP archive (zip-bomb
guard). The sum of all extracted file sizes must not exceed this limit.

---

#### `zip_max_files`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `500` |
| **Editable** | Yes — Admin (takes effect immediately) |

Maximum number of XML files that can be uploaded in a single ZIP batch. Files
inside subdirectories are not counted (they are skipped, not rejected).

---

### 6.4 Search & pagination

#### `search_results_per_page`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `10` |
| **Editable** | Yes — Admin |

Default page size for paginated list endpoints. Not actively read at runtime in
the current codebase — pagination is currently controlled by query parameters.
Reserved for future use as a platform-wide default.

---

### 6.5 Data retention

These settings are read by the daily scheduler job that purges old records.
Changes take effect on the next scheduler run (at most 24 hours later).

---

#### `audit_log_retention_days`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `90` |
| **Editable** | Yes — Admin |

Number of days to retain audit log entries. Rows with `created_at` older than
this are deleted by `purge_audit_log()` in `backend/app/core/scheduler.py`.

Reducing this value will not immediately delete old entries — they will be
removed on the next scheduled purge run.

**Consumed by**: `_get_retention("audit_log_retention_days", 90)` in
`app/core/scheduler.py` (fallback default: `90`).

---

#### `expired_sessions_retention_days`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `30` |
| **Editable** | Yes — Admin |

Number of days to retain expired session records after they become invalid.
Deleted by `purge_expired_sessions()` in `backend/app/core/scheduler.py`.

**Consumed by**: `_get_retention("expired_sessions_retention_days", 30)` in
`app/core/scheduler.py` (fallback default: `30`).

---

### 6.6 EVT viewer

#### `evt_enabled`

| | |
|---|---|
| **Type** | `bool` |
| **Default** | `false` |
| **Editable** | Yes — Admin |

**Global** switch for the EVT (Edition Visualization Technology) viewer.
When `false`, no collection can show the EVT button regardless of
per-collection settings. When `true`, the EVT button is shown for collections
that also have `evt_enabled = true` at the collection level, are `published`,
`is_public`, and contain exactly one document.

Both conditions must be met simultaneously:

```
show EVT = system_settings.evt_enabled
         AND collection.evt_enabled
         AND collection.status = 'published'
         AND collection.is_public
         AND doc_count = 1
```

**Consumed by**:
- `get_public_config()` → `UiConfigResponse.evt_enabled`
- Frontend: `useSettingStore.getSetting("evt_enabled")` in `CollectionDetailView.vue`
- Frontend: `useUiConfigStore.evt_enabled` in `PublicHomeSection.vue`

---

### 6.8 Website caching

#### `dynamic_cache_ttl`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `300` |
| **Editable** | Yes — Admin |
| **Unit** | seconds |

Cache TTL for DYNAMIC and HYBRID website pages. This setting is seeded and
stored but **not yet read at runtime** — the website service currently uses
a hardcoded constant of 300 seconds and notes this setting as a planned
integration point.

When wired, this value will be read from the database at request time to set
the `max-age` on dynamic page responses.

---

### 6.9 AI integration

All AI settings are read from the database at request time by
`backend/app/plugins/_native/ai/service.py`. Changes take effect on the next
API call — no restart required.

---

#### `ai_provider`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"disabled"` |
| **Editable** | Yes — Admin |
| **Valid values** | `disabled`, `openai`, `anthropic`, `gemini` |

Active AI provider. When `"disabled"`, all AI features are hidden in the UI
(`aiStore.config` is `null`, the AI panel button does not appear).

Changing this setting activates the corresponding provider immediately. The
API key for the selected provider must also be set.

**Consumed by**: `_get_provider()` and `get_ai_config()` in
`app/plugins/_native/ai/service.py`.

---

#### `ai_openai_api_key`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `""` (empty) |
| **Editable** | Yes — Admin |
| **Sensitive** | Yes — encrypted at rest, masked in API responses |

OpenAI API key. Required when `ai_provider = "openai"`. Stored encrypted using
AES with `JWT_SECRET` as the key. Never returned in plaintext by the API.

---

#### `ai_openai_model`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"gpt-4o"` |
| **Editable** | Yes — Admin |

OpenAI model name passed to the completions API. Any model available on the
configured API key can be used (e.g. `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`).

---

#### `ai_anthropic_api_key`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `""` (empty) |
| **Editable** | Yes — Admin |
| **Sensitive** | Yes — encrypted at rest, masked in API responses |

Anthropic API key. Required when `ai_provider = "anthropic"`.

---

#### `ai_anthropic_model`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"claude-opus-4-6"` |
| **Editable** | Yes — Admin |

Anthropic model name. Any model available on the configured API key can be used
(e.g. `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`).

---

#### `ai_gemini_api_key`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `""` (empty) |
| **Editable** | Yes — Admin |
| **Sensitive** | Yes — encrypted at rest, masked in API responses |

Google Gemini API key. Required when `ai_provider = "gemini"`.

---

#### `ai_gemini_model`

| | |
|---|---|
| **Type** | `string` |
| **Default** | `"gemini-1.5-pro"` |
| **Editable** | Yes — Admin |

Gemini model name (e.g. `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-2.0-flash`).

---

#### `ai_max_requests_per_hour`

| | |
|---|---|
| **Type** | `int` |
| **Default** | `20` |
| **Editable** | Yes — Admin |
| **Unit** | requests per user per hour |

Rate limit for AI streaming requests. Each authenticated user is allowed at
most this many AI requests per rolling 60-minute window. Requests beyond the
limit are rejected with `429 Too Many Requests`.

The rate-limit counter is stored in-memory (per backend process). In a
multi-process deployment, each process has its own counter — effective limit
is `ai_max_requests_per_hour × process_count`.

**Consumed by**: `_check_rate_limit()` and `get_ai_config()` in
`app/plugins/_native/ai/service.py`.

---

#### `ai_privacy_warning_enabled`

| | |
|---|---|
| **Type** | `bool` |
| **Default** | `false` |
| **Editable** | Yes — Admin |

When `true`, the AI panel displays a privacy disclaimer before the first
request in each session, reminding the user that document content is sent to
an external provider. Intended for deployments handling sensitive or
confidential documents.

**Consumed by**: `get_ai_config()` → `AiConfigResponse.privacy_warning_enabled`
→ `AiPanel.vue`.

---

## 7. How to add a new setting

1. **Add the seed entry** in `backend/app/db/seed.py`, inside `DEFAULT_SETTINGS`:

   ```python
   ("my_new_setting", "default_value", "string"),  # or "int" / "bool"
   ```

   Seed entries are idempotent — they are only inserted if the key does not
   already exist. Existing rows are never overwritten by seed.

2. **Document it here** — add an entry under the appropriate section in §6.
   Include: type, default, who can edit it, which backend functions read it,
   which frontend components consume it.

3. **Consume it in the backend** — read with:

   ```python
   # For non-sensitive settings:
   value = await get_setting(db, "my_new_setting")

   # For settings consumed by background services (not a router):
   value = await get_decrypted_setting(db, "my_new_setting")
   ```

   If the value must be part of the public UI config, add the key to
   `get_public_config()` in `backend/app/services/settings.py` and extend
   `UiConfigResponse` in `backend/app/schemas/settings.py`.

4. **Consume it in the frontend** — either:
   - Read via `settingStore.getSetting("my_new_setting")` (requires auth,
     Admin only)
   - Or read via `uiConfigStore.myNewSetting` if it was added to the public
     UI config

5. **Add i18n labels** in `frontend/src/locales/en.json` and `it.json` so the
   settings panel renders a readable label.

6. If the setting is **sensitive** (API key, password, secret), add the key to
   `SENSITIVE_KEYS` in `backend/app/core/encryption.py`.

> Re-running `make seed` after deploying will insert the new setting with its
> default value on any installation that does not already have it. Existing
> Admin-configured values are never overwritten.
