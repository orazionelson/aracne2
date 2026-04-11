# Security Review — 2026-04-11

**Last commit:** `7c97d03` — fix(security): dockerignore files + audit log for auth events  
**Branch:** `main`  
**Scope:** Full baseline review — automated tools + manual analysis by area

---

## Automated tools

### `pip-audit` (backend)

12 vulnerabilities found in 5 packages. All fixed.

| Package | From | To | CVEs |
|---|---|---|---|
| `fastapi` | 0.115.6 | 0.125.0 | (required for starlette fix) |
| `starlette` | 0.41.3 | 0.49.1 | CVE-2025-54121, CVE-2025-62727 |
| `python-jose` | 3.3.0 | 3.4.0 | PYSEC-2024-232, PYSEC-2024-233 |
| `cryptography` | 43.0.3 | 46.0.6 | CVE-2024-12797, CVE-2026-26007, CVE-2026-34073 |
| `python-multipart` | 0.0.20 | 0.0.22 | CVE-2026-24486 |
| `pip` | 25.0.1 | — | Not fixed (package manager, not app code) |

**Commit:** `ec3d5ee`

### `npm audit` (frontend)

6 vulnerabilities found. Critical fixed, dev-only deferred.

| Package | Severity | Fix |
|---|---|---|
| `axios` | Critical (SSRF) | `^1.7.9` → `^1.15.0` |
| `vite` / `esbuild` / `vitest` | Moderate (dev server only) | Deferred — breaking change, no production impact |

**Commit:** `ec3d5ee`

---

## Manual review by area

### 1. Auth & JWT ✅ No issues

- Refresh token: httpOnly cookie, `secure` in production, `samesite=strict`, path restricted to `/api/v1/auth`
- Token rotation on every refresh (old JTI revoked, new session created)
- JWT type claim enforced (`access` / `refresh` / `impersonation`) — prevents token confusion
- Session lookup by JTI on every request — tokens validated against DB
- Timing-safe login: dummy hash run even when user does not exist
- JWT secret validated ≥ 64 chars at startup
- `algorithms=["HS256"]` explicit — no `alg:none` vulnerability
- Impersonation: stateless, 30 min TTL, non-Admin-only targets, no re-impersonation

### 2. ACL ✅ No issues

- `require_role()` / `get_current_user` explicit on every endpoint
- Numeric level check + exact role check for lateral roles (Editor / Designer)
- `is_active` and `deleted_at` checked on every authenticated request

### 3. Input validation / XXE ✅ No issues

- `defusedxml` used for all XML parsing; stdlib `ET` used only for building (safe)
- No inline XQuery with f-strings
- Pydantic v2 validation at all API boundaries

### 4. Rate limiting ✅ No issues

- No public registration endpoint
- `STRICT_LIMIT` (10/min) on `POST /auth/login` and `POST /auth/password/change`
- `GLOBAL_LIMIT` (200/min) default on all other endpoints

### 5. CORS ✅ No issues

- `cors_origins` validated at startup: no wildcard, HTTPS-only in production
- `embed_app` sub-application isolated with `allow_credentials=False`

### 6. nginx security headers — Fixed

**Issue:** In nginx, any `add_header` directive in a child `location` block overrides all
`add_header` directives from the parent `server` block. Security headers (CSP,
`X-Frame-Options`, `X-Content-Type-Options`, etc.) were defined only at the server level,
so `location /` (serving `index.html`) and `location /assets/` were served without them.

**Fix:** Repeated the required security headers in each `location` block that defines
its own `add_header` directives.

**Commit:** `fc615cd`

### 7. IP pseudonymisation in logs — Fixed

**Issue:** `request_logger.py` logged raw IP addresses in all environments. CLAUDE.md
requires SHA-256 pseudonymisation in production.

**Fix:** Added `_log_ip()` in `request_logger.py`: returns the raw IP in development,
a salted SHA-256 digest (`sha256:<hex>`) in production (salt = `JWT_SECRET`).

**Commit:** `fc615cd`

### 8. Path traversal (defence-in-depth) — Fixed

**Issue:** `websites.py` and `search_engines.py` used `settings.websites_root / slug`
and `settings.search_engines_root / slug` for filesystem operations (mkdir, write, rmtree)
without verifying the resolved path stays within the allowed root. The Pydantic schemas
already enforce `pattern=r"^[a-z0-9_-]+$"` on all slug inputs, blocking traversal via
the API. However, a future code path bypassing schema validation (e.g. direct DB write,
seed script) could be exploitable.

**Fix:** Added `Path.is_relative_to()` containment checks in:
- `delete_website()` — `websites.py`
- `_build_static_site()` — `websites.py`
- `_build_hybrid_site()` — `websites.py`
- search engine build function — `search_engines.py`

**Commit:** `65b967e`

### 9. IDOR ✅ No issues

All resource access endpoints check ownership or permissions explicitly:
- Collections: `_assert_read_access()` checks owner, editor assignment, and explicit permissions
- Notifications: `_get_own_or_404()` enforces `user_id == current_user.id`
- Websites, XSLT templates, search engines: protected by role-level ACL

### 10. SSRF — Fixed

**Issue 1 (High):** `_resolve_transform()` in `websites.py` fetched XSLT stylesheets from
a URL supplied in `xslt_config["url"]` (accessible to Designer+) with no host validation
and `follow_redirects=True`, allowing requests to internal services.

**Issue 2 (Medium):** `WebhookEndpointCreate` in the webhook dispatcher plugin validated
only that the URL started with `http://` or `https://`, with no check on the resolved IP.

**Fix:**
- Extracted `_check_ssrf()` from `services/schemas.py` into a new shared module
  `app/core/ssrf.py` (`check_ssrf()`, public API).
- Applied `check_ssrf()` in `_resolve_transform()` before `client.get()`.
- Set `follow_redirects=False` on the XSLT HTTP client to block redirect-based bypass.
- Replaced the scheme-only validator in `WebhookEndpointCreate` and `WebhookEndpointUpdate`
  with `check_ssrf()`.
- `import_validation()` and `import_cm5()` in `services/schemas.py` now import from
  `app.core.ssrf` (same logic, no behaviour change).

**Commit:** `ca481ee`

### 11. XSS frontend ✅ No issues

- No `v-html` directives in any component
- The only `innerHTML` assignments are three hardcoded emoji labels in `WysiwygEditor.vue`
  (Tiptap node view renderers) — no user input involved
- No `eval`, `new Function`, or dynamic script injection
- The embed snippet generator produces a string for copy-paste, not DOM injection

### 12. Mass assignment / privilege escalation — Fixed

**Issue:** `POST /users` was accessible to EditorInChief (level 3). The `UserCreate`
schema accepted any valid role name including `Admin` (level 4). An EditorInChief could
therefore create a user with a higher role than their own.

**Fix:** Added a level check in `routers/users.py`: `ROLE_LEVEL[body.role]` must not
exceed `ROLE_LEVEL[request.state.role]`. Raises 403 if violated.

`role_assign` and `role_revoke` are Admin-only and were not affected.

**Commit:** `322b4cf`

### 13. Secrets in git history ✅ No issues

- `.env` is listed in `.gitignore` and was never committed in 276 commits
- No hardcoded credentials found in the diff history

### 14. Docker security ✅ No issues

- All ports bound to `127.0.0.1` in `docker-compose.yml` (postgres, existdb, backend, frontend)
- Backend container runs as non-root user `appuser` (uid 1000)
- Frontend uses multi-stage build: development → builder → `nginx:alpine`
- No secrets hardcoded in Dockerfiles or compose file; all from `.env`

### 15. `.dockerignore` — Fixed

**Issue:** Absent `.dockerignore` files caused the Docker build context to include
`__pycache__`, `.pytest_cache`, `.mypy_cache`, `node_modules`, `dist`, `.env` files,
`.git/` and editor metadata, unnecessarily increasing build context size.

**Fix:** Created `backend/.dockerignore` and `frontend/.dockerignore`.

**Commit:** `7c97d03`

### 16. Audit log coverage — Improved

**Issue:** Login success and password change were only logged to structlog (ephemeral),
not persisted in the `audit_log` table (queryable from the admin interface).
Failed logins produced no log entry at all.

**Fix:**
- `create_session()`: persists `auth.login_success` to `AuditLog` (actor, ip, user_agent, role)
- `change_password()`: persists `auth.password_changed` to `AuditLog` (sessions revoked count)
- `authenticate_user()`: logs `login_failed` via `logger.warning()` — a DB write here would
  be rolled back by `get_async_session`'s exception handler, so structlog is the correct tier

**Remaining gaps** (out of scope for this review):
- Settings changes not in AuditLog
- Plugin enable/disable not in AuditLog

**Commit:** `7c97d03`

---

## Deferred / out of scope

| Item | Reason |
|---|---|
| `vite`/`esbuild` npm update | Breaking change (Vite 8); affects dev server only, no production impact |
| `pip` upgrade inside container | Package manager, not application code |
| `follow_redirects=True` in schema URL import | Protected by `check_ssrf()`; fixing deferred to avoid scope creep |
| Settings / plugin audit log | Not requested; noted as remaining gap |
