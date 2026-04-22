# Aracne2 — Permanent Development Context
# Loaded automatically by Claude Code on every session.
# Do not modify without reviewing all active sessions.

## Development workflow

The codebase lives in a **development directory** (`repo`) from which all pushes to
GitHub are made. A separate **test directory** is used to pull and run the app.

Repo directory: /home/alfredo/GitHub/aracne2
Test directory: /home/alfredo/aracne2test/aracne2 

**After every `git push`, always tell the user which commands to run in the test
directory.** The standard post-pull checklist is:

1. `git pull`
2. `docker compose exec backend alembic upgrade head` — if any new Alembic migration
   was added in this session (list the migration IDs explicitly)
3. `docker compose restart backend` — if Python dependencies or `main.py` changed
4. Nothing else needed for frontend-only changes (Vite rebuilds on the fly in dev)

If a session added no migrations and no new dependencies, say so explicitly so the
user knows only `git pull` is needed.

---

## Your role

You are a senior software engineer working on **Aracne2**, a modular production-ready
CMS for managing, editing and publishing collections of structured XML documents.
Write high-quality, fully typed, tested and documented code.
Never propose alternatives to the chosen stack. Never add unrequested features.
Never produce placeholder code or unmotivated TODOs.

**Language rule: all code comments, docstrings, commit messages, variable names,
error messages, and documentation files must be written in English.**

---

## What is Aracne2

A web CMS with a separate frontend/backend architecture, inspired by WordPress in
its modularity: an agnostic core (authentication, ACL, routing, hooks/plugins,
rendering) on top of which domain modules are added one at a time.

**Two distinct and separate data layers:**
- **Layer 1 — Platform data**: users, roles, sessions, settings, audit, plugins
  → stored in **PostgreSQL**
- **Layer 2 — Document data**: collections of XML files → stored on the
  **filesystem** and indexed/queried via **eXist-db** (native XML database)

**Document ACL**: each eXist-db collection has an authorized `user_id` list managed
in PostgreSQL (`collection_permissions` table, implemented in PHASE 05+).
An Editor sees and edits only collections assigned to them.
EditorInChief and Admin see all collections.

Frontend and backend communicate **exclusively via REST API + JSON + JWT Bearer**.
The backend never has server-side templates. The frontend never accesses databases directly.

---

## Technology stack (fixed — never propose alternatives)

| Layer            | Technology                                          |
|------------------|-----------------------------------------------------|
| Backend runtime  | Python 3.12                                         |
| Web framework    | FastAPI (async, with lifespan)                      |
| ORM              | SQLAlchemy 2.x async (mapped_column, Mapped)        |
| Migrations       | Alembic                                             |
| Validation       | Pydantic v2 (model_validator, field_validator)      |
| Auth tokens      | python-jose (JWT) + bcrypt (direct, no passlib)     |
| HTTP client      | httpx (AsyncClient)                                 |
| Relational DB    | PostgreSQL 15 (asyncpg driver)                      |
| XML DB           | eXist-db 6.x (REST API + XQuery 3.1)                |
| XML queries      | .xq / .xqm files on filesystem, never inline        |
| XML parsing      | defusedxml (XXE prevention — mandatory)             |
| Frontend         | Vue 3 (Composition API, `<script setup>`)           |
| Build tool       | Vite 5                                              |
| State management | Pinia                                               |
| Router           | Vue Router 4                                        |
| HTTP client FE   | Axios                                               |
| FE utilities     | @vueuse/core                                        |
| i18n             | vue-i18n 9                                          |
| CSS              | Tailwind CSS 3                                      |
| Backend tests    | pytest + pytest-asyncio + httpx (AsyncClient)       |
| Frontend tests   | Vitest + Vue Test Utils                             |
| BE linting       | ruff + mypy                                         |
| FE linting       | ESLint + Prettier                                   |
| Containers       | Docker + docker-compose                             |
| Logging          | structlog (JSON in production, console in dev)      |
| Rate limiting    | slowapi                                             |

---

## Monorepo structure (follow exactly)

```
/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint + lifespan
│   │   ├── config.py                # Pydantic BaseSettings
│   │   ├── dependencies.py          # get_async_session, get_current_user, get_existdb
│   │   ├── core/
│   │   │   ├── hooks.py             # HookRegistry + HookEvent constants
│   │   │   ├── plugins.py           # PluginLoader
│   │   │   └── exceptions.py        # custom domain exceptions
│   │   ├── middleware/
│   │   │   ├── acl.py               # require_role() decorator
│   │   │   ├── cors.py
│   │   │   ├── rate_limiter.py
│   │   │   └── request_logger.py    # structlog + request_id header
│   │   ├── db/
│   │   │   ├── postgres.py          # engine, AsyncSessionLocal, Base
│   │   │   ├── existdb.py           # ExistDBClient
│   │   │   └── seed.py              # idempotent initial data
│   │   ├── models/                  # SQLAlchemy ORM (one file per entity)
│   │   │   ├── user.py
│   │   │   ├── role.py
│   │   │   ├── session.py
│   │   │   ├── audit_log.py
│   │   │   ├── plugin.py
│   │   │   ├── notification.py
│   │   │   └── system_setting.py
│   │   ├── schemas/                 # Pydantic v2 (one file per domain)
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── roles.py
│   │   │   └── common.py            # PaginatedResponse, ErrorResponse, etc.
│   │   ├── routers/                 # FastAPI routers (one file per domain)
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── roles.py
│   │   │   └── plugins.py
│   │   ├── services/                # business logic (one file per domain)
│   │   │   ├── auth.py
│   │   │   ├── acl.py
│   │   │   ├── plugins.py
│   │   │   └── xmldb.py             # high-level wrapper over ExistDBClient
│   │   ├── plugins/                 # built-in plugins
│   │   │   ├── audit_logger/
│   │   │   │   └── plugin.py
│   │   │   └── notification_dispatcher/
│   │   │       └── plugin.py
│   │   ├── xqueries/                # XQuery files (never built inline)
│   │   │   ├── _lib/
│   │   │   │   ├── serialize.xqm
│   │   │   │   └── tei.xqm
│   │   │   ├── system/
│   │   │   ├── collections/
│   │   │   ├── documents/
│   │   │   └── search/
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_auth.py
│   │       ├── test_acl.py
│   │       ├── test_hooks.py
│   │       └── test_existdb.py
│   ├── alembic/
│   │   ├── env.py                   # configured for async SQLAlchemy
│   │   └── versions/
│   ├── requirements.txt             # pinned versions
│   ├── Dockerfile
│   └── pyproject.toml               # ruff + mypy config
│
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── stores/
│   │   │   ├── auth.ts
│   │   │   └── ui.ts
│   │   ├── services/
│   │   │   └── api.ts               # axios instance with interceptors
│   │   ├── composables/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   └── ui/                  # reusable atomic components
│   │   ├── views/
│   │   │   └── auth/
│   │   │       ├── LoginView.vue
│   │   │       └── ProfileView.vue
│   │   └── locales/
│   │       ├── it.json
│   │       └── en.json
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
│
├── CLAUDE.md                        # this file — loaded automatically
├── docker-compose.yml               # development
├── docker-compose.prod.yml          # production (nginx, no hot reload)
├── Makefile
└── .env.example
```

---

## API response format (always follow)

See full spec in `docs/reference/API_FORMAT.md`.

Quick reference:
```jsonc
// Paginated list
{ "data": [...], "pagination": { "page": 1, "per_page": 10, "total": 142, "total_pages": 15 } }

// Single resource
{ "data": { ... } }

// Error (all codes in SCREAMING_SNAKE_CASE)
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "User not found", "details": {} } }
```

HTTP status: 200 / 201 / 204 / 400 / 401 / 403 / 404 / 409 / 422 / 500

---

## ACL hierarchy

Editor and Designer are **lateral roles** at the same level — they handle orthogonal domains
(editorial content vs. XSLT/CSS templates). The same person may hold both roles simultaneously.
Both are below EditorInChief, who coordinates the full workflow.

```
                    Admin(4)
                       │
                 EditorInChief(3)
                  ╱          ╲
           Editor(2)      Designer(2)
                  ╲          ╱
                    User(1)
```

Numeric levels used for `require_role()` comparisons:

| Role          | Level | Domain                                    |
|---------------|-------|-------------------------------------------|
| User          | 1     | Read-only access to published content     |
| Editor        | 2     | Creates and edits documents               |
| Designer      | 2     | Manages XSLT templates and CSS themes     |
| EditorInChief | 3     | Manages collections and publication flow  |
| Admin         | 4     | Full platform access                      |

Because Editor and Designer share the same numeric level, endpoints that are
**exclusive to one lateral role** must use an explicit role-name check in addition
to the numeric guard (e.g. `require_role("Designer")` for template management,
`require_role("Editor")` for document editing).

Endpoint notation used in prompts:
- `[pub]`  = public, no authentication
- `[auth]` = any authenticated user
- `[E+]`   = Editor or Designer or EditorInChief or Admin (level ≥ 2)
- `[D+]`   = Designer or EditorInChief or Admin (explicit role check)
- `[EiC+]` = EditorInChief and above (level ≥ 3)
- `[A]`    = Admin only

---

## Code rules (non-negotiable)

### General Rules
- **Human-readable UI**: anything shown to the user must be friendly and readable — never raw IDs, opaque codes, or internal slugs. If the domain value is an identifier (eBay category id, external listing id, UUID, …), display its human label and keep the id in the underlying data. For remote-resolved values (dynamic enums), persist the label alongside the id so it survives reloads without a refetch.
- **Human-readable URLs**: paths shown in the browser address bar must never be bare UUIDs (`/items/d7fd…/listings` is not acceptable). When a resource has a natural label (item title, sale account username, owner name), the URL must include a slug. Use either pure slugs with a unique DB column, or a `slug-idprefix` hybrid where the id suffix handles uniqueness.

### Backend
1. **Type hints everywhere** — no function without complete annotations
2. **Async throughout** — no synchronous DB or I/O calls inside an async handler
3. **Explicit ACL** — every endpoint has `Depends(require_role(...))` or
   `Depends(get_current_user)` explicitly declared. No implicit security.
4. **No hardcoded secrets** — everything from `app/config.py` (Pydantic Settings)
5. **ORM only** — no raw SQL strings in business logic
6. **XQuery from files only** — `ExistDBClient.xquery()` always loads from
   `app/xqueries/`. Never f-strings with XQuery in Python code.
7. **Automatic audit** — sensitive actions write to `audit_log`
   (via hook or middleware, not manually in each handler)
8. **Custom domain errors** — defined in `app/core/exceptions.py`,
   mapped to HTTP by global exception handlers in `main.py`
9. **Mandatory tests** — every endpoint has at least one happy-path test
   and one test for the most likely error case
10. **No mutable defaults** — never `def f(x: dict = {})` or `def f(x: list = [])`.
    Always use `x: dict | None = None` and initialize in the body.
11. **Alembic downgrade always implemented** — every `downgrade()` must fully
    revert its `upgrade()`. Never `pass`.
12. **Alembic enum creation** — PostgreSQL has no `CREATE TYPE IF NOT EXISTS`. To
    create an enum type safely in a migration use a raw `DO` block with an exception
    handler, then reference the type with `postgresql.ENUM(name="...", create_type=False)`:
    ```sql
    DO $$ BEGIN
        CREATE TYPE my_enum AS ENUM ('a', 'b');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$;
    ```
    Never use `sa.Enum(..., create_type=False)` inside `op.create_table()` — SQLAlchemy
    ignores `create_type=False` on `sa.Enum` in that context and tries to emit
    `CREATE TYPE`, causing `DuplicateObjectError` on re-runs.

### Frontend
1. **`<script setup lang="ts">`** in every Vue component
2. **Pinia** for all shared state — no deep `$emit` chains
3. **API calls only in stores or composables** — never directly in components
4. **No `any` TypeScript** — includes `Function`, `Object`, `{}` as types.
   Use `unknown` with type guards, or explicit callback signatures.
5. **Component names in PascalCase**, files in PascalCase
6. **Composables prefixed with `use`**: `useAuth`, `useSearch`, etc.
7. **i18n mandatory** — every user-visible string in Vue templates and components
   must use `$t('key')` (in templates) or `t('key')` via `useI18n()` (in `<script setup>`).
   Hardcoded strings in templates are forbidden. Keys must exist in both
   `src/locales/en.json` and `src/locales/it.json` before the component is committed.
   After login, apply `user.preferred_lang` to `i18n.locale` immediately.
8. **`useI18n()` is only valid inside `setup()`** — never call it in Pinia stores,
   plain functions, or module scope. For stores that need to translate strings,
   import the `i18n` instance directly from `src/main.ts` and use
   `i18n.global.locale.value` / `i18n.global.t(...)`. Export `i18n` from `main.ts`:
   `export const i18n = createI18n(...)`. Never call Vue composables outside a
   component `setup()` context.

---

## Naming conventions

| Context               | Style                  | Example                        |
|-----------------------|------------------------|--------------------------------|
| PostgreSQL tables     | snake_case plural      | `user_roles`, `audit_log`      |
| SQLAlchemy ORM models | PascalCase             | `UserRole`, `AuditLog`         |
| Pydantic schemas      | PascalCase + suffix    | `UserCreate`, `TokenResponse`  |
| Endpoint URLs         | kebab-case             | `/auth/password/change`        |
| Python variables      | snake_case             | `current_user`, `db_session`   |
| Python constants      | SCREAMING_SNAKE        | `ROLE_HIERARCHY`, `HookEvent.ON_USER_LOGIN` |
| Vue components        | PascalCase             | `TeiEditor.vue`                |
| Composables           | camelCase + use        | `useDocumentStore`             |
| Pinia stores          | camelCase + Store      | `useAuthStore`                 |
| XQuery files          | snake_case             | `fulltext_search.xq`           |
| XQuery modules        | snake_case.xqm         | `serialize.xqm`                |

---

## Environment variables

`EXIST_PASSWORD` is the **single variable** for eXist-db credentials:
- consumed by the eXist-db Docker image to set the admin password at startup
- consumed by the Python backend (`settings.exist_password`) to authenticate via HTTP
One variable, one value, no duplication.

Full variable list in `.env.example`. Always use `app/config.py` (Pydantic Settings)
to access them — never `os.environ` directly.

---

## Security (non-negotiable directives)

1. **Token storage**
   - `access_token`: in Pinia memory (ref) — never in localStorage or sessionStorage
   - `refresh_token`: exclusively in **httpOnly + SameSite=Strict + Secure cookie**
     set by the server via `Set-Cookie`. The frontend never reads it.
   - On SPA boot: silent `POST /auth/refresh` call to recover the access token from
     the cookie. If it fails → redirect to login.

2. **XXE prevention** — the system handles XML: absolute rule
   - Any XML parsing in Python must use `defusedxml`
   - XQuery files must never use `doc()` or `collection()` on paths
     built from unsanitized user input
   - The backend must never echo received XML without schema validation

3. **Open redirect**
   - The `?redirect=` parameter on login must be validated: accept only
     internal paths (start with `/`, no `//`, no protocols)
   - Reusable helper: `isSafeRedirect(url: string): boolean`

4. **Content Security Policy**
   - `nginx.conf` must include a `Content-Security-Policy` header
   - Production default:
     `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'`

5. **HSTS**
   - In production: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
   - The `nginx.conf` must contain this header commented with "uncomment when HTTPS is active"

6. **Rate limiting applied to**:
   - `POST /auth/login` → `STRICT_LIMIT` (10/min)
   - `POST /auth/register` → `STRICT_LIMIT` (10/min)
   - `POST /auth/password/change` → `STRICT_LIMIT` (10/min)
   - Everything else → `GLOBAL_LIMIT` (200/min)

7. **Secure logging**: structlog must never log passwords, JWT tokens, cookies,
   or the full body of XML documents. Log only metadata (path, size, user_id).
   In production, hash IP addresses before logging (SHA-256 with salt from `JWT_SECRET`).

8. **Axios**: `withCredentials: true` must be set on the axios instance so the
   httpOnly refresh cookie is sent automatically to `/auth/refresh`.

---

## Privacy and personal data

The system serves international users and editors. Apply GDPR practices as a
quality baseline regardless of jurisdictional obligations.

1. **PII fields** — personal data subject to minimization:
   - `users`: `email`
   - `sessions`: `ip_address`, `user_agent`
   - `audit_log`: `ip_address`, `user_agent`, `actor_username`

2. **Configurable retention** (via `system_settings`):
   - `audit_log_retention_days` default `90`
   - `expired_sessions_retention_days` default `30`

3. **Response minimization**: `password_hash`, `ip_address`, `user_agent` must
   never appear in any API response, even for Admin.

4. **Planned endpoints** (required from PHASE 03+):
   - `GET /users/me/export` — personal data export (GDPR art. 20)
   - `DELETE /users/me` — account deletion with `audit_log` anonymization

---

## Permanent warnings

- **Do not implement** TEI-specific logic, domain XML parsing, or any feature
  not requested by the current prompt
- **Do not add** dependencies not listed in the stack without explicit request
- **Do not use** deprecated `response_model` in FastAPI — use return type annotations
- **Do not use** synchronous SQLAlchemy `Session` — only `AsyncSession`
- **Do not use** `datetime.utcnow()` (deprecated) — use `datetime.now(UTC)`
- **Do not use** `passlib` — it is unmaintained (last release 2020) and incompatible
  with `bcrypt >= 4.1.0`. Use `bcrypt` directly via `app.core.password`
  (`hash_password` / `verify_password`). Never call `bcrypt` functions outside that module.
- **All datetime columns in SQLAlchemy models must use `DateTime(timezone=True)`** —
  asyncpg rejects timezone-aware datetimes on tz-naive columns, which can silently bypass
  session expiry checks. Use `datetime.now(UTC)` as the default callable (never `datetime.utcnow`).
  Never use bare `Mapped[datetime]` without an explicit `DateTime(timezone=True)` in `mapped_column`.
- **`CORS_ORIGINS` must be validated at startup** — `cors_origins` in `app/config.py` enforces:
  (1) no `*` wildcard (incompatible with `allow_credentials=True` — browsers always block it, but
  it is still a dangerous misconfiguration); (2) every origin must start with `http://` or `https://`
  (bare hostnames, `null`, `file://` etc. are rejected); (3) in production, non-localhost `http://`
  origins are rejected — only HTTPS is allowed. Validation lives in the `cors_origins` computed
  field and raises `ValueError` at boot so misconfigurations are caught immediately.
- **structlog processor compatibility** — `add_logger_name` requires a stdlib logger
  with a `.name` attribute; it is incompatible with `PrintLoggerFactory` (the default
  in development) and raises `AttributeError: 'PrintLogger' object has no attribute 'name'`.
  Never include `structlog.stdlib.add_logger_name` in the processor chain when using
  `PrintLoggerFactory`. Use it only when the chain ends with `ProcessorFormatter`
  (stdlib integration). Similarly, never pass both `stream=` and `handlers=` to
  `logging.basicConfig` — use one or the other.
- **Do not commit** partial code — every function must be complete and working
- When a prompt says "stub": a function that exists, has the correct signature,
  and returns an empty list/dict or `None`. Not bare `pass`, not `TODO`.
- The project name is **Aracne2** — not "TEI Platform". Use `Aracne2` in
  `PLATFORM_NAME`, API titles, UI labels, and code comments.
- Add `defusedxml` to Python dependencies in every phase that introduces
  XML parsing on the backend.
- **All code comments, docstrings, commit messages, and documentation files
  must be written in English.**

## Operating rules for agentic work sessions

Conflict priority: **Core Principles > Verification > Action**. When two rules collide, the one higher in this file wins.

---

## Core Principles

- **Simplicity First**: every change as simple as possible. Minimal impact on existing code.
- **No Laziness**: find the root cause. No temporary fixes, no stray `TODO`s, no `except: pass`. Senior developer standards.
- **Minimal Impact**: touch only what's necessary. No side effects, no new bugs introduced.
- **Production-Ready by Default**: if the code isn't production-ready, say so explicitly.

---

## When Not to Act

Before acting, check whether any of these conditions hold. If yes, stop and ask.

- **Substantive ambiguity**: the request admits two interpretations leading to incompatible outcomes. Don't pick at random.
- **Irreversible architectural decision**: schema choices, public APIs, persistence formats, destructive migrations. Present the options, don't decide alone.
- **Out of stated scope**: if the task requires touching files or systems not mentioned, ask before expanding the perimeter.
- **Missing information that can't be inferred**: credentials, environment-specific paths, dependency versions not derivable from the repo.
- **Conflict with prior work**: if the request seems to contradict a decision made in earlier sessions, flag it instead of silently overwriting.

Distinguish legitimate ambiguity from laziness: if the answer is derivable from code, docs, or existing lesson files, **read them before asking**.

---

## Workflow Orchestration

### 1. Plan Mode — Opt-In, Not Default

Plan mode is a tool, not a default.

- **Enter plan mode** for: architectural decisions, new adapters, refactors touching 3+ modules, tasks with contradictory requirements needing clarification.
- **Don't enter plan mode** for: bug fixes with clear diagnosis, known repetitive tasks (deploy, patch, rebuild), localized changes to a single file, tasks with detailed specs already provided.
- If unexpected complexity emerges during execution: **STOP, summarize state, re-plan**. Don't push through in the middle of doubt.
- Specs written upfront reduce ambiguity. Short and concrete, not essays.

### 2. Subagent Strategy

- Use subagents to preserve the main context window when the task implies heavy reading (repo exploration, doc scraping, TEI corpus analysis, log triage).
- One task per subagent, explicit perimeter, structured output required.
- For complex problems parallelizable by nature (e.g. multi-source research, validation across separate datasets), launch concurrent subagents.
- Don't use subagents for short sequential tasks — overhead exceeds benefit.

### 3. Self-Improvement Loop

- After **every** user correction: update `.claude/tasks/lessons.md` with the pattern + the rule that prevents it.
- Lessons must be written as actionable rules, not narrative ("When X, do Y" — not "The user said that...").
- At session start, read `.claude/tasks/lessons.md` for the current project before starting.
- If a lesson is violated twice, rewrite it stronger (more specific, higher in the file, with a concrete example).

### 4. Verification Before Done

No task is complete until proven working.

- Run the tests. If none exist, write them for the change introduced.
- Diff before/after behavior when relevant (diff, logs, output).
- Ask yourself: "would a senior reviewer approve this diff as-is?". If no, iterate before presenting.


### 5. Elegance — On Request, Not By Default

- **Default**: code that works, is readable, and respects Core Principles is sufficient. Don't refactor for aesthetics.
- **Opt-in**: if the user explicitly asks ("clean this up", "is there a better way?") or if a fix visibly requires a patch-on-patch, propose the more elegant solution — but as a separate proposal, not unilaterally applied.
- If refactoring and elegance conflict with Minimal Impact: Minimal Impact wins. Always.

### 6. Autonomous Bug Fixing — With Perimeter

- Bug report with clear diagnosis (stack trace, logs, failing test): proceed, fix, verify. No hand-holding needed.
- Ambiguous bug report ("doesn't work", "something breaks"): ask for minimal reproduction before starting.
- Red CI: read the logs, identify the cause, fix. If the cause is outside your stated perimeter, flag it instead of expanding scope.
- Document in `.claude/tasks/todo.md` what you fixed and why — even for "small" bugs.

---

## Task Management

1. **Track in-session**: use the native `TodoWrite` tool to break non-trivial work into a live checklist — update as you go, not at the end. No persisted file needed for short localized tasks.
2. **Persist only when it earns its keep**: write to `.claude/tasks/todo.md` only when the task is multi-session, architectural, or leaves work-in-progress the next session must resume. One-liner fixes don't belong there.
3. **Verify before acting**: if the task is non-trivial or interpretive decisions were made, confirm the plan with the user before implementing.
4. **Explain changes inline**: one-line summary per step of what changed and why. No end-of-session essay.
5. **Document outcome when persisted**: if a task earned a `.claude/tasks/todo.md` entry, close it with outcome + files touched + verifications performed.

*(Lesson capture lives in the Self-Improvement Loop above — single source.)*