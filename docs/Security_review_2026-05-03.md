# Security Review — 2026-05-03

**Previous review:** `Security_review_2026-04-29.md` (last covered commit: `7ea7301`)
**Current HEAD on `development`:** `f89a939`
**Branch:** `development`
**Scope:** Periodic dependency audit + manual review of the surfaces
that landed since the previous review (Milestone 2 audit log + fixity
layer; Milestone 3 `policy_pages` plugin + capability roles; the
GDPR posture rework). The previous review was driven by the
private→public flip; this one is the routine quarter-tick the
`Notable items` list called out.

---

## Automated tools

### `pip-audit`

Run via an ephemeral `python:3.12-slim` container against
`backend/requirements.txt`. **Four** advisories across two packages:

| Package | Version | Advisory | Severity | Fix |
|---|---|---|---|---|
| `PyJWT` | 2.10.1 | CVE-2026-32597 — `crit` (RFC 7515 §4.1.11) header bypass; tokens with unrecognised critical extensions are accepted instead of rejected | MED | 2.12.0 |
| `Jinja2` | 3.1.4 | CVE-2024-56326 — sandbox escape via `str.format` reference passed through a custom filter | MED (sandbox-only) | 3.1.5 |
| `Jinja2` | 3.1.4 | CVE-2024-56201 — sandbox-bypass when an attacker controls *both* template content and template filename | MED (sandbox-only) | 3.1.5 |
| `Jinja2` | 3.1.4 | CVE-2025-27516 — sandbox escape via `|attr` filter on string `format` | MED (sandbox-only) | 3.1.6 |

### `npm audit` (frontend)

Eight moderate advisories, **two patchable today**, six in the
`vite`/`vitest`/`esbuild` chain that need a major-version triple
bump (same posture as `Security_review_2026-04-29.md` — deferred):

| Package | Severity | Reachability | Fix posture |
|---|---|---|---|
| `postcss` <8.5.10 | MOD | XSS via unescaped `</style>` in CSS Stringify | Patch — bumped (this commit) |
| `follow-redirects` <=1.15.11 | MOD | Custom auth headers leaked on cross-domain redirect | Patch — `npm audit fix` lock-refresh in test directory |
| `vite` / `vitest` / `esbuild` / `@vitest/mocker` / `@vitest/coverage-v8` / `vite-node` | MOD | dev-tooling only, none production-reachable | Defer — major bump (vite 5 → 8) is breaking; track for next tooling sweep |

---

## Findings

### 1. Policy-pages public render: missing bleach pass — **MED** ✅ Fixed `<this commit>`

**Files:**
- [backend/app/plugins/policy_pages/router.py:301](backend/app/plugins/policy_pages/router.py#L301) (`public_render`)

**Description:**

The Markdown-to-HTML pipeline for `/policies/<slug>` rendered the
operator-supplied policy body via `MarkdownIt("commonmark",
{"html": False})` and passed the result straight to the SPA's
`v-html`. `html: False` blocks raw HTML in Markdown, but
markdown-it's default link validator does **not** filter dangerous
URL schemes (`javascript:`, `data:`). A malicious or
compromised PolicyManager (singleton capability role; rare but in
the threat model) could embed `[click me](javascript:alert(1))`
in a localised field; the rendered `<a href="javascript:…">`
would reach every public visitor and execute on click.

The same content path in the `help` plugin is already protected
by a `bleach.clean()` pass with explicit tag / attribute /
protocol allow-lists. The policy_pages router was missing the
equivalent.

**Threat model context:** the actor must already hold
`PolicyManager` (or be Admin). Admin-issued malicious content is
out of scope of every threat model, but `PolicyManager` is the
first non-Admin role with public-page write authority, so
defence-in-depth applies — we should not assume "PolicyManager is
trusted enough" in the same way as Admin.

**Fix:**

Mirror the help plugin's posture in
[router.py:_PUBLIC_RENDER_ALLOWED_TAGS / _ATTRS / _PROTOCOLS](backend/app/plugins/policy_pages/router.py).
The render is now `MarkdownIt → bleach.clean(..., protocols=
["http", "https", "mailto"])`. `javascript:` and `data:` URLs
are stripped; non-allowlisted tags (`<script>`, `<iframe>`,
`<style>`, …) are dropped. `bleach` is already in
`requirements.txt`; no new dependency.

---

### 2. PyJWT 2.10.1 — `crit` header bypass — **MED** ✅ Fixed `<this commit>`

**File:** [backend/requirements.txt](backend/requirements.txt)

**Description:**

CVE-2026-32597. RFC 7515 §4.1.11 says a JWS containing a `crit`
array of critical extensions the recipient does not understand
**must** be rejected. PyJWT 2.10.1 silently accepts such tokens.

**Reachability in Aracne2:** `app.services.auth.decode_token`
calls `jwt.decode(token, secret, algorithms=["HS256"])`. We do
not produce JWTs with `crit` headers ourselves; an attacker
forging one can only do so if they already hold the platform's
HS256 secret (in which case JWT integrity is moot). The
practical impact in our deployment is therefore limited.
Still — the patch is one-line and the upstream advisory rates it
"split-brain verification in mixed-library deployments" as the
realistic abuse path; bumping closes the residual.

**Fix:** `PyJWT==2.10.1` → `PyJWT==2.12.0`. Backwards-compatible
patch release per the upstream changelog.

---

### 3. Jinja2 3.1.4 — three sandbox-escape CVEs — **MED (sandbox-only)** ✅ Fixed `<this commit>`

**File:** [backend/requirements.txt](backend/requirements.txt)

**Description:**

CVE-2024-56326, CVE-2024-56201, CVE-2025-27516 — three
sandbox-escape vectors. **All require an attacker who controls the
content (or filename) of a Jinja2 template.**

**Reachability check** — every Jinja2 use in the platform:

| Caller | Templates loaded from | Author |
|---|---|---|
| `services/email.py` | `app/email_templates/` | Maintainer (in-image) |
| `plugins/policy_pages/router.py` | `app/plugins/policy_pages/public_md/` | Maintainer (in-image) |
| `plugins/nl_search/prompts/` | maintainer-controlled prompt files | Maintainer (in-image) |

No code path lets a user upload, edit, or otherwise control a
Jinja2 template body. The CVEs are **not exploitable** in
Aracne2's threat model. Bump for hygiene anyway — Jinja2 3.1.4 →
3.1.6 is patch-level.

---

### 4. postcss <8.5.10 — CSS Stringify XSS — **MOD (build-tooling)** ✅ Fixed `<this commit>`

**File:** [frontend/package.json](frontend/package.json)

**Description:**

CVE: PostCSS escapes `</style>` incorrectly when stringifying.
Reachability is **build-time only** — runs during the Vite build
in the dev container, not at request time on a live deployment.
Production frontends serve pre-built static assets; an attacker
cannot inject CSS at runtime that PostCSS would re-stringify.

**Fix:** Direct dep floor `"postcss": "^8.4.49"` →
`"^8.5.10"`. After `npm install` in the test directory the
lockfile resolves to the patched line. `follow-redirects` —
transitive — is fixed as a side-effect of the same lock refresh
(`npm audit fix`).

---

### 5. vite / vitest / esbuild chain — **MOD (dev-only)** ⏸ Deferred

**File:** [frontend/package.json](frontend/package.json)

**Description:**

Six advisories chain off `esbuild` < 0.25.0 (vite 5 → 8 major
bump territory). The previous review tracked them as "dev-tooling,
none production-reachable"; the situation is unchanged. Vite 8
landed on npm with breaking changes to the plugin API; promoting
the bump means re-validating every Vue / Vitest plugin we use.

**Decision:** defer to the next tooling sweep — likely paired
with a future esbuild advisory that rates HIGH or with a
contributor-driven Vite 8 PR. Track via `npm audit` quarterly.

---

## Manual code review — surfaces landed since 2026-04-29

Reviewed:

- `backend/app/routers/audit_log.py` (M2)
- `backend/app/routers/fixity.py` (M2)
- `backend/app/routers/capabilities.py` (M3)
- `backend/app/routers/gdpr_admin.py` (M1 residual / GDPR rework)
- `backend/app/routers/users.py` (changes to `/me/export` +
  `/me/anonymise-request`)
- `backend/app/plugins/policy_pages/router.py` (M3, with public
  surfaces)
- `backend/app/plugins/policy_pages/service.py` (M3)
- `backend/app/services/audit_log.py` (M2)
- `backend/app/services/fixity.py` (M2)
- `backend/app/services/roles.py` (M3)
- `backend/app/services/gdpr.py` (M1 residual)
- `backend/alembic/versions/0078..0082` migrations
- `backend/app/middleware/acl.py` `require_capability` addition
- `backend/app/plugins/_native/email_dispatcher/service.py`
  (the new `on_gdpr_request_submitted` listener)
- The `frontend/src/views/admin/{AuditLogView,FixityView,
  PolicyPagesView,GdprView}.vue` admin surfaces

### What I checked

- **ACL gating on every new route**: every admin endpoint sits
  behind `Depends(require_role(min_role="Admin"))` or
  `Depends(require_capability("PolicyManager"))`. Public
  endpoints (`/policies` and `/policies/{url_slug}`) are
  intentionally anonymous and filter to `is_published=True`
  before returning anything. **Clean.**
- **SQL-injection patterns**: every query uses SQLAlchemy ORM
  with parametrised binds. No `f"…{user_input}…"` strings
  reach `db.execute`. The audit-log `q` filter uses
  `column.ilike(f"%{q}%")` — that interpolates into a Python
  string passed as a parameter, not into the SQL itself.
  **Clean.**
- **Sensitive-field minimisation**: the GDPR export
  (`services/gdpr.export_personal_data`) explicitly excludes
  `password_hash`, the SHA-256-hashed IP, bcrypt digests of
  PATs, and bcrypt digests of password-reset tokens. The
  audit-log detail endpoint excludes `ip_address` and the raw
  `user_agent`. The fixity endpoint exposes only hash hex-digits
  and timestamps. **Clean.**
- **Anonymise transactional invariant**:
  `anonymise_user_metadata` rewrites `users` row, sweeps
  `audit_log.actor_username`, sweeps `audit_log.target_label`,
  revokes sessions + PATs, deletes outstanding
  password-reset tokens — all in a single transaction; a
  partial failure rolls back. The legal-trail
  `user.anonymised` audit row is the only place the placeholder
  ↔ original mapping is preserved. **Clean.**
- **Singleton role transfer**: `transfer_singleton_role` revokes
  the previous holder and grants the target in the same
  transaction. Idempotent on "target already holds it" (no audit
  spam). **Clean.**
- **Public render bleach gap on policy pages**: the one finding
  reported above. Fixed in this commit.
- **Email dispatcher GDPR notification**: best-effort,
  fire-and-forget pattern matches the rest of the dispatcher.
  The hook handler catches every exception so a misconfigured
  email channel never blocks the queue row from landing.
  **Clean.**
- **NL search surface (M1)**: not modified since the previous
  review; spot-checked the `services.nl_search.orchestrator`
  citation enforcement (drops any `(slug, filename)` not in the
  tool-call whitelist) — still in place.

### Confirmed clean

| Area | Verdict |
|---|---|
| Direct hardcoded secrets | None tracked; only `changeme_*` placeholders in `.env.example` |
| Personal data in code | None in tracked files; review of every M3 / GDPR doc passes |
| Admin endpoints without auth gates | None — every `@router.{verb}` on the new admin routers carries the `_admin` / `_writer` dependency |
| SQL injection | No raw-SQL string interpolation; ORM-only on every new path |
| Public render XSS | Now bleach-sanitised after fix #1 |
| Audit-log payload sensitivity | Free-form JSONB but operator-controlled; no raw IP / UA / hash leakage |
| Missing transactions on multi-step writes | None observed; `transfer_singleton_role`, `anonymise_user_metadata`, `save_draft`+`publish_version` all flush within a single async transaction |

---

## Resolution summary

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | MED | Policy-pages public render missing bleach pass | ✅ Fixed (this commit) |
| 2 | MED | `PyJWT` 2.10.1 `crit` header bypass | ✅ Fixed (this commit) |
| 3 | MED (sandbox-only) | `Jinja2` 3.1.4 three sandbox-escape CVEs — not exploitable, hygiene bump | ✅ Fixed (this commit) |
| 4 | MOD (build-tooling) | `postcss` <8.5.10 + transitive `follow-redirects` | ✅ Fixed (this commit) — package.json floor; lock refresh in test dir |
| 5 | MOD (dev-only) | vite / vitest / esbuild major-bump chain | ⏸ Deferred — same posture as 2026-04-29 |

After this commit lands and the test directory pulls + rebuilds:

```bash
git pull
docker compose up -d --build backend     # PyJWT 2.12 + Jinja2 3.1.6 land in the image
cd frontend && npm install                # postcss + follow-redirects lockfile refresh
docker compose up -d --build frontend     # if the frontend image bakes node_modules
```

a follow-up `pip-audit` returns 0 findings; `npm audit` returns
6 (the deferred dev-tooling chain).

---

## Notable items

- The next routine review tick should land **after the async
  task queue ships** (DEFERRED §1) — that introduces a new
  worker container with its own attack surface (Redis broker,
  worker process, task pickling) worth a dedicated audit.
- The `bleach` allow-list on the policy-pages public render
  should grow `<img>` only if a future template needs it; for
  now images are not in scope (operator policies are text-only).
- Consider adding a `linkify`-aware filter for ORCID URIs in
  the editorial_board / expert_directory templates so the
  ORCID hex-id field auto-links to `https://orcid.org/<id>`
  without the operator having to type the URL. Out of scope of
  this review; track on the polish backlog.
