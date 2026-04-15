# Security Review — 2026-04-15

**Previous review:** `Security_review_2026-04-14.md` (last covered commit: `0b8c574`)  
**Current HEAD:** `5539be8`  
**Branch:** `main`  
**Scope:** Differential review — 63 commits since `0b8c574`  
**New features under review:** Bibliobuilder (AI bibliography extraction + versioned storage),
AI panel multi-turn chat (Discuss mode, XSLT AI panel), Zones module (TEI `<zone>`
text-image alignment), website editing improvements (XSLT Edit tab, `website_url` field,
public home with website links), authenticated dashboard.

---

## Automated tools

### `pip-audit`

No new Python dependency changes in the 63 commits. No new vulnerabilities.

### `npm audit`

No frontend dependency changes. Deferred `vite`/`esbuild` upgrade still out of scope.

---

## Findings

---

### 1. `website_url` stored XSS via `javascript:` href in public home — **HIGH** ✅ Fixed f3f5fb1

**Backend:** [backend/app/schemas/websites.py](backend/app/schemas/websites.py#L50)  
**Frontend:** [frontend/src/components/PublicHomeSection.vue](frontend/src/components/PublicHomeSection.vue#L165-L173)

**Description:**

`website_url` is stored in the `websites` table and returned by the public
collections API as `website_link`. The backend schema accepts any string up to
512 characters with no scheme validation:

```python
# schemas/websites.py — WebsiteCreate and WebsiteUpdate
website_url: str | None = Field(None, max_length=512)   # no scheme check
```

The frontend binds the value directly to the `href` attribute of a public link:

```html
<!-- PublicHomeSection.vue:165-173 (also :249) -->
<a
  v-if="col.website_link"
  :href="col.website_link"       <!-- no sanitisation -->
  target="_blank"
  rel="noopener noreferrer"
>
```

Vue does not sanitize `:href` bindings. A Designer (or compromised Designer
account) can set `website_url = "javascript:alert(document.cookie)"`, publish
the website with `show_in_public_home = true`, and any anonymous user who clicks
"Visit the site" on the public home executes the payload.

`rel="noopener noreferrer"` only prevents the opened page from accessing
`window.opener`; it does **not** block `javascript:` execution.

Note: the value is correctly HTML-escaped when written into static build meta
tags (`_html.escape()` in `websites.py:1670`) — that path is safe. The
vulnerability is exclusively in the API response → frontend `:href` binding.

**Fix (backend):** Add a URL scheme validator to both `WebsiteCreate` and
`WebsiteUpdate`:

```python
from urllib.parse import urlparse
from pydantic import field_validator

@field_validator("website_url", mode="before")
@classmethod
def validate_website_url(cls, v: str | None) -> str | None:
    if not v:
        return v
    v = v.strip()
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("website_url must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("website_url must include a valid hostname")
    return v
```

**Fix (frontend — defence in depth):** Add a safety guard in
`PublicHomeSection.vue` before binding:

```typescript
function isSafeUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}
```

```html
<a v-if="isSafeUrl(col.website_link)" :href="col.website_link" ...>
```

---

### 2. AI rate-limit check committed after HTTP 200 — **MEDIUM** ✅ Fixed f3f5fb1

**File:** [backend/app/plugins/_native/ai/router.py](backend/app/plugins/_native/ai/router.py#L95-L133)  
**Service:** [backend/app/plugins/_native/ai/service.py](backend/app/plugins/_native/ai/service.py#L200)

**Description:**

`POST /ai/complete` returns a `StreamingResponse` immediately. The generator
`event_stream()` does not run until Starlette starts streaming the body — by
which point the HTTP status `200 OK` has already been committed. The rate-limit
check (`_check_rate_limit`) is called inside the generator:

```python
# router.py — ai_complete
return StreamingResponse(event_stream(), ...)   # 200 committed here

# event_stream() — runs after headers are sent
async for chunk in service.stream_completion(   # rate limit checked inside this
    db, body.prompt_slug, body.context, ...
):
```

Two consequences:

1. **Wrong HTTP status on breach**: a user who has exceeded the hourly limit
   receives `200 OK` with `{"error": "AI rate limit exceeded"}` in the body
   instead of `429 Too Many Requests`. Clients that inspect status codes (not
   body) to decide retry logic will loop indefinitely.

2. **TOCTOU race on simultaneous requests**: concurrent requests all read
   `AiRequestLog` before any entries are committed, see `count = 0`, and all
   pass the check. The DB-level rate limit can be bypassed by firing N requests
   in rapid succession.

**Fix:** Check the rate limit in the route handler, before the
`StreamingResponse` is created:

```python
@router.post("/complete")
async def ai_complete(
    body: AiCompleteRequest,
    current_user: Annotated[User, _editor],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> StreamingResponse:
    try:
        await service._check_rate_limit(db, current_user)
    except service.AiRateLimitError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail=exc.message)

    async def event_stream() -> AsyncGenerator[str, None]:
        ...
    return StreamingResponse(event_stream(), ...)
```

The `_check_rate_limit` call can be kept inside `stream_completion` as a
second guard; removing it there is not needed.

---

### 3. AI chat history and context have no size bounds — **MEDIUM** ✅ Fixed f3f5fb1

**File:** [backend/app/schemas/ai.py](backend/app/schemas/ai.py#L55-L63)

**Description:**

```python
class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str                          # no max_length

class AiCompleteRequest(BaseModel):
    prompt_slug: str
    context: dict[str, str]              # no max entries, no max value length
    history: list[AiChatMessage] = []    # no max items
```

The hourly rate limit (default 20 requests) counts API *calls*, not tokens. A
single call with a 50-turn history of 10 000-character messages consumes far
more tokens — and cost — than the limit intends. An authenticated Editor could
amplify AI API costs significantly within a single request.

**Fix:** Add reasonable caps at the schema level:

```python
from pydantic import Field

class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=32_000)

class AiCompleteRequest(BaseModel):
    prompt_slug: str
    context: dict[str, str] = Field(default_factory=dict, max_length=20)
    history: list[AiChatMessage] = Field(default=[], max_length=40)
```

---

### 4. Zone coordinates have no geometric validity check — **MEDIUM** ✅ Fixed f3f5fb1

**File:** [backend/app/schemas/facsimile.py](backend/app/schemas/facsimile.py#L6-L28)

**Description:**

```python
class ZoneIn(BaseModel):
    xml_id: str
    ulx: int    # no minimum, no maximum
    uly: int
    lrx: int
    lry: int
```

Pydantic validates the types (must be integers) but does not check:
- Non-negative values: `ulx = -999999` is accepted.
- Geometric sanity: `lrx < ulx` (inverted rectangle) is accepted.
- Reasonable bounds: coordinate values in the billions are accepted.

Negative or inverted coordinates are stored in the TEI XML and returned by the
API. If any downstream processing (e.g. future image cropping, IIIF region
generation) relies on these values without re-validating, it could produce
unexpected results or errors.

**Fix:**

```python
from pydantic import field_validator, model_validator

class ZoneIn(BaseModel):
    xml_id: str
    ulx: int = Field(..., ge=0)
    uly: int = Field(..., ge=0)
    lrx: int = Field(..., ge=0)
    lry: int = Field(..., ge=0)

    @model_validator(mode="after")
    def check_geometry(self) -> "ZoneIn":
        if self.lrx <= self.ulx:
            raise ValueError("lrx must be greater than ulx")
        if self.lry <= self.uly:
            raise ValueError("lry must be greater than uly")
        return self
```

---

### 5. XSLT content not validated as XML before storage — **LOW** ✅ Fixed f3f5fb1

**File:** [backend/app/schemas/xslt_templates.py](backend/app/schemas/xslt_templates.py)

**Description:**

The `content` field in `XsltTemplateCreate` and `XsltTemplatePatch` is
validated only for non-emptiness. A Designer can save a syntactically invalid
or non-XML string as a stylesheet. This fails only at transform time (when a
website build runs), not at storage time, producing a late and potentially
confusing error.

This is a data-quality issue rather than a direct security risk: Designers are
a trusted role, the XSLT is processed by lxml (not a server executing
arbitrary code), and the existing XXE analysis from the previous review
(already noted as acceptable for trusted Designer input) still applies.

**Fix:**

```python
@field_validator("content")
@classmethod
def content_is_valid_xml(cls, v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("content cannot be blank")
    import defusedxml.ElementTree as ET
    try:
        ET.fromstring(v)
    except Exception as exc:
        raise ValueError(f"XSLT content is not valid XML: {exc}")
    return v
```

---

### 6. Public collections endpoint has no explicit rate-limit decorator — **LOW** ✅ Fixed f3f5fb1

**File:** [backend/app/plugins/_native/collections/router.py](backend/app/plugins/_native/collections/router.py#L93)

**Description:**

`GET /collections/public` is an unauthenticated endpoint that accepts a
`search` query parameter and returns paginated results from PostgreSQL. It falls
through to the global `GLOBAL_LIMIT` (200 requests/minute). No `@limiter.limit`
decorator is applied explicitly.

200 requests/minute is a generous limit for an unauthenticated public listing.
Compared to the GeoNames and VIAF proxies (fixed to 30/min in `88c497b`), this
endpoint — which touches the database for every request — is less protected.

**Fix:**

```python
from app.middleware.rate_limiter import limiter

@router.get("/public")
@limiter.limit("60/minute")
async def collections_public(request: Request, ...):
```

Note: `slowapi` requires `request: Request` as a named parameter when using
`@limiter.limit`.

---

## Confirmed clean — new features

| Area | Verdict |
|---|---|
| Bibliobuilder ACL | EiC+ (`_eic`) required for all write operations; service double-checks with `_assert_eic(role)` |
| Bibliobuilder version IDs | Auto-incremented integers from DB (`MAX(version) + 1`); no filesystem path component, no traversal risk |
| Bibliobuilder public bibliography | `bibliography_public_get` correctly gates on `col.is_public` AND `col.status == published` before returning any data |
| AI API key | Read via `get_decrypted_setting()` (encrypted at rest); not logged at any level; not exposed in `GET /ai/config` response |
| AI response persistence | Responses are streamed to the client only; nothing is written to DB or disk — no stored XSS risk |
| AI prompt template injection | `_fill_template` uses `str.format_map(context)`; context values are user-controlled strings but only substituted into key positions defined by the admin-controlled template — not a Python code injection risk |
| Zones XML parsing | `defusedxml.fromstring()` used for all reads; stdlib `ET.SubElement` used for building new elements (safe, no parsing) |
| Zones surface_id matching | Matched with exact string comparison against `xml:id` attributes; no XPath, no injection risk |
| Zones service ACL | `_assert_read_access` and `_assert_write_access` correctly enforced at service level |
| XSLT default download | Hardcoded bundle path (`Path(__file__).parent.parent / "xslt" / "tei_generic.xsl"`); no user-supplied path; D+ ACL |
| Bibliography HTML render | Text extracted from XML nodes and passed through `_html.escape()` — stored XSS prevented |
| Bibliography XML parsing | `defusedxml.ElementTree` used in `_build_bibliography_content()` — XXE-safe |
| `website_url` in static builds | Passed through `_html.escape()` before insertion into `<meta content="...">` — safe in that context |
| Migrations 0042–0045 | All `downgrade()` functions fully implemented; no new PostgreSQL enum types; no raw SQL |
| Health endpoint | Returns status + environment string only; no DB version, no host info, no secrets |

---

## Deferred (carried over)

| Item | Reason |
|---|---|
| `vite`/`esbuild` npm upgrade | Breaking change (Vite 8); dev server only |
| `pip` upgrade inside container | Package manager, not application code |
| Settings / plugin events in audit log | Out of scope |
| Magic byte validation for media uploads | No execution path; extension + Content-Type double-check adequate |

---

## Resolution summary

All 6 findings fixed in commit `f3f5fb1`.

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | HIGH | `website_url` stored XSS | ✅ Fixed f3f5fb1 |
| 2 | MEDIUM | AI rate-limit after HTTP 200 | ✅ Fixed f3f5fb1 |
| 3 | MEDIUM | AI payload size unbounded | ✅ Fixed f3f5fb1 |
| 4 | MEDIUM | Zone coordinates unchecked | ✅ Fixed f3f5fb1 |
| 5 | LOW | XSLT not validated as XML | ✅ Fixed f3f5fb1 |
| 6 | LOW | `/collections/public` no rate limit | ✅ Fixed f3f5fb1 |
