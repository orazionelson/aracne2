# Security Review — 2026-04-16

**Previous review:** `Security_review_2026-04-15.md` (last covered commit: `67a90a8`)  
**Current HEAD:** `21a5fe9`  
**Branch:** `main`  
**Scope:** Differential review — 27 commits since `67a90a8`  
**New features under review:** Named Entity Index (public view, admin CRUD, tag config,
reindex), Custom Homepage CSS (upload/serve/delete/propagate), `home_show_login_button`
toggle, CSS class reference for public views.

---

## Automated tools

### `pip-audit`

No new Python dependency changes in the 27 commits. No new Python vulnerabilities.

### `npm audit`

**New vulnerabilities found.**

| Package | Severity | Advisory | Affected range |
|---------|----------|----------|----------------|
| `axios` | **CRITICAL** (CVSS 10.0) | GHSA-fvcv-3m26-pcqx — Unrestricted Cloud Metadata Exfiltration via Header Injection | `>=1.0.0 <1.15.0` |
| `axios` | **CRITICAL** (CVSS 9.9) | GHSA-3p68-rc4w-qgx5 — NO_PROXY Hostname Normalization Bypass / SSRF | `>=1.0.0 <1.15.0` |
| `follow-redirects` | moderate | GHSA-r4q5-vmmm-2653 — Auth header leak to cross-domain redirect | `<=1.15.11` |
| `vite` | moderate | GHSA-4w7w-66w2-5vf9 — Path traversal in `.map` handling | dev server only |
| `esbuild` | moderate | GHSA-67mh-4wv8-2f99 — Dev server CORS bypass | dev server only |

`package.json` specifies `"axios": "^1.15.0"` (patched), but the lockfile resolves
`node_modules/axios` to **1.14.0** (vulnerable). `npm install` was not re-run after
the version bump in `package.json`, leaving the installed artifact on the old version.

`vite`, `esbuild`, and `follow-redirects` issues are unchanged from previous reviews
(dev server only, or deferred upgrade).

---

## Findings

---

### 1. `axios` lockfile stale — 1.14.0 (vulnerable) installed instead of 1.15.0 — **CRITICAL** ✅ Fixed 0779959

**File:** [frontend/package-lock.json](frontend/package-lock.json)

**Description:**

`npm audit` reports two critical vulnerabilities in `axios < 1.15.0`:

- **GHSA-fvcv-3m26-pcqx** (CVSS 10.0): Unrestricted Cloud Metadata Exfiltration via
  Header Injection Chain. An attacker who can influence outgoing HTTP headers can
  exfiltrate cloud metadata (e.g. AWS IMDSv1 `http://169.254.169.254/`).
- **GHSA-3p68-rc4w-qgx5** (CVSS 9.9): NO_PROXY hostname normalization bypass leading
  to SSRF. Affects environments that use a proxy with a blocklist.

`package.json` already specifies `^1.15.0`. The lockfile, however, still pins
`1.14.0`. The mismatch means the installed version in `node_modules/` and in any
Docker image built from the current lockfile is the vulnerable one.

**In-app impact:**

The Aracne2 frontend uses axios for all API calls. The header injection and SSRF
vectors require an attacker to control headers or proxy configuration. In the current
deployment this is a lower-exploit risk (axios runs in a browser, not server-side),
but Docker images built from the stale lockfile have the vulnerable package baked in,
and the `CVSS 10.0` score makes this a mandatory patch regardless.

**Fix:**

```bash
cd frontend
npm install   # regenerates package-lock.json to resolve axios@1.15.0+
```

Commit the updated `package-lock.json`. Verify with:

```bash
npm list axios   # should show axios@1.15.x
```

---

### 2. Public `GET /entities` — no rate limit, no `q` length cap, no `per_page` bound — **MEDIUM** ✅ Fixed 0779959

**File:** [backend/app/plugins/_native/named_entities/router.py](backend/app/plugins/_native/named_entities/router.py#L174-L191)

**Description:**

The public, unauthenticated entity listing endpoint has three missing guards:

```python
@router.get("")          # no @limiter.limit()
async def list_entities(
    db: _DbDep,
    entity_type: Annotated[str | None, Query(alias="type")] = None,
    q: str | None = None,                   # no max_length
    collection_slug: str | None = Query(default=None, alias="collection_slug"),
    page: int = 1,
    per_page: int = 30,                     # no le= cap
) -> PaginatedResponse:
```

The service translates `q` into `NamedEntity.canonical_form.ilike(f"%{q}%")`.  A
very long `q` (e.g. 100 KB) creates an equally large LIKE pattern that PostgreSQL
must evaluate against every row before the `ORDER BY + LIMIT`. Combined with the
missing `per_page` cap (an attacker can request `per_page=999999`) and no
`@limiter.limit()` decorator, an unauthenticated caller can generate sustained
expensive database load at 200 requests/minute.

The pattern is identical to the `GET /collections/public` issue fixed in `f3f5fb1`.

**Fix:**

```python
from app.middleware.rate_limiter import limiter
from fastapi import Request

@router.get("")
@limiter.limit("60/minute")
async def list_entities(
    request: Request,
    db: _DbDep,
    entity_type: Annotated[str | None, Query(alias="type")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    collection_slug: str | None = Query(default=None, alias="collection_slug"),
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
) -> PaginatedResponse:
```

---

### 3. Public `GET /entities/{id}/occurrences` — no `per_page` bound — **LOW** ✅ Fixed 0779959

**File:** [backend/app/plugins/_native/named_entities/router.py](backend/app/plugins/_native/named_entities/router.py#L194-L213)

**Description:**

```python
@router.get("/{entity_id}/occurrences")
async def list_entity_occurrences(
    entity_id: uuid.UUID,
    db: _DbDep,
    collection: str | None = None,
    page: int = 1,
    per_page: int = 20,     # no le= cap
) -> PaginatedResponse:
```

`per_page` has no upper bound. Sending `per_page=99999` forces a full table scan
of `entity_occurrences` joined to `collections`. Less severe than finding 2 (no
free-text LIKE) but still an unguarded door for an unauthenticated caller.

**Fix:**

```python
@router.get("/{entity_id}/occurrences")
async def list_entity_occurrences(
    entity_id: uuid.UUID,
    db: _DbDep,
    collection: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse:
```

---

### 4. CSS and logo file uploads have no size limit — **LOW** ✅ Fixed 0779959

**File:** [backend/app/routers/settings.py](backend/app/routers/settings.py#L86-L98)  
**File:** [backend/app/services/settings.py](backend/app/services/settings.py#L114-L134)

**Description:**

Both `upload_homepage_css()` and `upload_logo()` call `await file.read()` with no
byte cap:

```python
# settings router — POST /settings/homepage-css  (Admin only)
content = await file.read()          # no limit
(media / _CSS_FILENAME).write_bytes(content)

# settings router — POST /settings/logo  (Admin only)
content = await file.read()          # no limit
(media / f"logo{ext}").write_bytes(content)
```

A compromised Admin account could upload a multi-gigabyte file, exhausting disk
space in `MEDIA_DIR` and crashing the backend. The fix is cheap and the endpoints
are already Admin-gated.

**Fix (service layer):**

```python
_MAX_CSS_BYTES  = 512 * 1024   # 512 KB
_MAX_LOGO_BYTES = 2 * 1024 * 1024   # 2 MB

async def upload_homepage_css(content: bytes, filename: str, actor: User) -> ...:
    if len(content) > _MAX_CSS_BYTES:
        raise DomainValidationError("FILE_TOO_LARGE", "CSS file must be ≤ 512 KB")
    ...

async def upload_logo(db, content: bytes, filename: str, actor: User) -> ...:
    if len(content) > _MAX_LOGO_BYTES:
        raise DomainValidationError("FILE_TOO_LARGE", "Logo must be ≤ 2 MB")
    ...
```

---

### 5. `GET /settings/homepage-css/file` and `GET /settings/logo/file` have no explicit rate limit — **LOW** ✅ Fixed 0779959

**File:** [backend/app/routers/settings.py](backend/app/routers/settings.py#L68-L80), [L101-L111](backend/app/routers/settings.py#L101-L111)

**Description:**

Both public file-serving endpoints fall through to the 200 req/min global limit.
Each call opens and streams a file from disk. This is more expensive per-request
than a settings read but cheaper than a database query. Nonetheless, explicit limits
are cheap to add and consistent with the project's approach to public endpoints.

**Fix:**

```python
@router.get("/logo/file")
@limiter.limit("120/minute")
async def settings_logo_file(request: Request) -> FileResponse:
    ...

@router.get("/homepage-css/file")
@limiter.limit("120/minute")
async def settings_homepage_css_file(request: Request) -> FileResponse:
    ...
```

---

### 6. `EntityTagConfig.tags` has no length bounds — **LOW** ✅ Fixed 0779959

**File:** [backend/app/plugins/_native/named_entities/schemas.py](backend/app/plugins/_native/named_entities/schemas.py#L50-L67)

**Description:**

```python
class EntityTagConfig(BaseModel):
    tags: list[str]     # no max items

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one tag must be configured")
        cleaned = [t.strip() for t in v]
        if any(not t for t in cleaned):
            raise ValueError("Tag names cannot be empty")
        return cleaned
```

The `tags` list has no cap on the number of items, and individual tag strings have
no max_length. The tags are joined with spaces and passed as the `$tags` XQuery
external variable:

```python
tags = " ".join(config)   # could be very long
await existdb.xquery("named_entities/extract_document.xq", {"doc_path": ..., "tags": tags})
```

An EiC+ could store a list of thousands of tags, causing every re-index call to
pass an extremely long string to eXist-db. EiC+ is a trusted role, but the cap
is a good hygiene constraint.

**Fix:**

```python
from pydantic import Field

class EntityTagConfig(BaseModel):
    tags: list[str] = Field(..., min_length=1, max_length=50)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v]
        if any(not t for t in cleaned):
            raise ValueError("Tag names cannot be empty")
        for tag in cleaned:
            if len(tag) > 64:
                raise ValueError("Tag names must be ≤ 64 characters")
        return cleaned
```

---

## Confirmed clean — new features

| Area | Verdict |
|---|---|
| XQuery tag injection | `$tags` is bound as a typed XQuery external variable, not interpolated into source; `local-name() = $tag-seq` treats values as strings — no XQuery injection vector |
| Named entity public ACL | `get_public_entities()` always filters `Collection.status == published` AND `Collection.is_public.is_(True)` before returning data |
| Entity occurrences public ACL | `get_entity_occurrences(public_only=True)` applies the same published+public filter |
| Admin entity mutations | All `/entities/admin/*` routes require `Admin` role; tag-config requires `EiC+` |
| Entity XSS | `canonical_form`, `raw_form`, `context` are returned as JSON strings; defusedxml used to parse XQuery output — no stored XSS risk |
| Custom CSS content | CSS cannot execute JavaScript in modern browsers; served as `text/css`; Admin-only upload; no CSP bypass introduced |
| CSS propagation | `usePublicCustomCss` appends a `<link>` to `<head>` — no `innerHTML` / `eval` — safe DOM manipulation |
| CSS URL hardcoded | `const CSS_URL = '/api/v1/settings/homepage-css/file'` — not user-controlled, no open redirect |
| `home_show_login_button` | Boolean toggle; no injection vector |
| Logo upload extension check | Only `.png .jpg .jpeg .gif .svg .webp` accepted; stored under fixed name `logo{ext}` — no path traversal |
| CSS upload extension check | Only `.css` accepted; stored as fixed `custom_homepage.css` — no path traversal |
| `home_propagate_css` | Boolean setting, no user input injected into DOM or HTML |
| Entity deduplication | `_upsert_entity()` uses `func.lower()` case-insensitive lookup; no duplicate creation |
| Authority ref validation | `_clean_authority_ref()` rejects internal `#`-prefixed refs; accepts only strings with `:` — no injection via authority URI |
| Migrations 0046 | `downgrade()` reverts enum→varchar change; no unsafe raw SQL |

---

## Deferred (carried over)

| Item | Reason |
|---|---|
| `vite`/`esbuild` npm upgrade | Breaking change (Vite 6→8 path); dev server only |
| `pip` upgrade inside container | Package manager, not application code |
| Settings / plugin events in audit log | Out of scope |
| Magic byte validation for media uploads | No execution path; extension + Content-Type double-check adequate |
| `follow-redirects` moderate | Transitive dependency of axios; resolved by axios 1.15.0 upgrade (finding 1) |

---

## Resolution summary

All 6 findings fixed in commit `0779959`.

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | CRITICAL | axios 1.14.0 lockfile stale | ✅ Fixed 0779959 |
| 2 | MEDIUM | `GET /entities` no rate limit / no bounds | ✅ Fixed 0779959 |
| 3 | LOW | `GET /entities/{id}/occurrences` no per_page cap | ✅ Fixed 0779959 |
| 4 | LOW | CSS and logo uploads no size limit | ✅ Fixed 0779959 |
| 5 | LOW | Logo/CSS file endpoints no rate limit | ✅ Fixed 0779959 |
| 6 | LOW | EntityTagConfig.tags no bounds | ✅ Fixed 0779959 |
