# Security Review — 2026-04-27

**Previous review:** `Security_review_2026-04-16.md` (last covered commit: `21a5fe9`)
**Current HEAD:** `916931e`
**Branch:** `main`
**Scope:** Differential review — 197 commits since `21a5fe9`
**New surfaces under review:** authority-lookup plugin family (Wikidata, ORCID, ROR,
VIAF, GeoNames, GND, CERL, Peripleo, Getty AAT, OpenAlex, Trismegistos, CrossRef);
deposit plugin family (Zenodo, Internet Archive, Codeberg, GitHub, GitLab, Dataverse);
plugin auto-cabling capabilities (`inline_authority`, `collection_deposit`,
`website_deposit`); plugin hot-mount/unmount; user avatar upload + Markdown bio;
public homepage cover text WYSIWYG (`home_intro_html`); homepage media folder;
public document download (TEI / PDF source); bibliography filename linkification;
website Wikidata hover preview; AI prompt scope-driven cabling and Bibliobuilder
quota lift; search-engines iframe + adaptive header colours; `/sites/<slug>` URL
flattening (drop `/api/v1`); public-search iframe escape and CSS inheritance;
i18n bare-`@<word>` escaping fix.

---

## Automated tools

### `pip-audit`

No new Python dependencies since `21a5fe9`. No new Python vulnerabilities.

### `npm audit`

`axios` is on **1.15.0** in both `package.json` and `package-lock.json` — both
critical CVEs from the previous review are closed.

Remaining moderate findings (all unchanged from prior reviews, all dev-only):

| Package | Severity | Notes |
|---------|----------|-------|
| `vite` | moderate | Path traversal in optimised-deps `.map` handling — dev server only |
| `esbuild` | moderate | Dev-server CORS bypass — dev server only |
| `postcss` | moderate | `</style>` XSS in stringify output — build-time only, attacker would need write access to source CSS |
| `follow-redirects` | moderate | Auth header leak — transitive of dev tooling |
| `vitest` / `@vitest/*` / `vite-node` | moderate | Pulled by the same dev-tooling chain |

All eight items are deferred (same rationale as the previous reviews: dev server
tooling, no production exposure). No new criticals.

---

## Findings

---

### 1. `PUT /settings/home-intro` stores unsanitised HTML rendered with `v-html` on the public homepage — **LOW**

**File:** [backend/app/routers/settings.py:215-237](backend/app/routers/settings.py#L215-L237)
**Frontend sink:** [frontend/src/components/PublicHomeSection.vue](frontend/src/components/PublicHomeSection.vue) (`v-html="introHtml"`)

**Description:**

The cover-text WYSIWYG (`5e8caf4`) writes whatever HTML the admin submits straight
into `system_settings.home_intro_html`:

```python
class HomeIntroBody(BaseModel):
    html: str               # no max_length, no sanitisation

@router.put("/home-intro")
async def settings_home_intro_update(body: HomeIntroBody, ...):
    row = SystemSetting(key="home_intro_html", value=body.html, type="string")
    db.add(row)             # body.html written verbatim
```

`PublicHomeSection.vue` renders the value via `v-html`, so any HTML in the body
runs as DOM on every visitor's browser.

**Mitigation in place:** the production nginx CSP — `default-src 'self'; script-src
'self'; img-src 'self' data:` — blocks inline scripts, inline event handlers
(`onerror="…"`), `javascript:` URIs, and external-origin images. So the
exploitable surface in a CSP-enforced deployment is reduced to:

- Phishing via `<a href="https://attacker.example">…</a>` — CSP does not block
  navigations.
- Same-origin redirect chains via `<meta http-equiv="refresh" …>`.
- Layout disruption / spoofing via crafted markup.

In **dev mode** (no CSP, `vite` server) the full XSS surface is open.

**In-app impact:**

The endpoint is `Admin`-only. The closed-audience trust model
([feedback_manual_security_review.md], [project_closed_audience.md]) means an
unintended attacker would need to compromise an admin account first. The defence
here is depth: a sanitiser closes the gap between "admin compromise" and
"persistent XSS on every visitor", and also protects against accidental paste of
copy-from-CMS markup that pulls in tracking pixels or third-party widgets the
admin didn't realise were there.

**Fix:**

Run `body.html` through `bleach.clean()` at the service boundary. `bleach==6.2.0`
is already in `backend/requirements.txt` (used by `app/plugins/help/service.py`).

```python
import bleach

_INTRO_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "h2", "h3", "h4",
    "a", "img", "figure", "figcaption", "hr",
}
_INTRO_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
}
_INTRO_ALLOWED_PROTOCOLS = ["http", "https", "media"]
_INTRO_MAX_BYTES = 64 * 1024  # 64 KB

@router.put("/home-intro")
async def settings_home_intro_update(body: HomeIntroBody, ...):
    if len(body.html.encode("utf-8")) > _INTRO_MAX_BYTES:
        raise DomainValidationError("FILE_TOO_LARGE", "Cover text must be ≤ 64 KB")
    cleaned = bleach.clean(
        body.html,
        tags=_INTRO_ALLOWED_TAGS,
        attributes=_INTRO_ALLOWED_ATTRS,
        protocols=_INTRO_ALLOWED_PROTOCOLS,
        strip=True,
    )
    row.value = cleaned
```

The 64 KB cap is a hygiene constraint in addition (no current cap; the WYSIWYG
in the SPA imposes none either).

---

### 2. File-upload endpoints buffer the full body in memory before checking the size cap — **LOW-MEDIUM**

**Files:**
- [backend/app/routers/users.py:101-114](backend/app/routers/users.py#L101-L114) (`POST /users/me/avatar`)
- [backend/app/routers/websites.py:544-568](backend/app/routers/websites.py#L544-L568) (`POST /websites/{slug}/media`)
- [backend/app/routers/settings.py](backend/app/routers/settings.py) (homepage media, logo, custom CSS — partly addressed in 04-16 review)

**Description:**

Every upload handler does `payload = await file.read()` and only then checks the
per-endpoint cap. nginx caps the request body at **50 MB** globally
(`client_max_body_size 50m` in `nginx.conf`), but each per-endpoint cap is much
smaller: 1 MB (avatar), 8 MB (website media), 2 MB (logo), 512 KB (CSS). The
delta between 50 MB and the per-handler cap is buffered in process memory before
being rejected.

```python
# routers/users.py
@router.post("/me/avatar")
async def upload_my_avatar(file: UploadFile, current_user, db):
    payload = await file.read()    # reads up to 50 MB before any cap check
    data = await upload_avatar(db, current_user, payload, file.filename or "avatar")
```

`upload_avatar()` then runs `if len(payload) > _AVATAR_MAX_BYTES: raise …`, but
the bytes are already in memory at that point. With 200 req/min global rate
limit and any authenticated user able to call the avatar endpoint, an attacker
with a single low-privilege account can drive ~10 GB/min of memory pressure
through avatar uploads alone, with no work proportional to that on their side.

**In-app impact:**

Authenticated DoS. The closed-audience model softens it (every account is
vetted), but the cost-asymmetry (50 MB allocated server-side per cheap client
request) is a real footgun that survives the trust model: a single
mis-configured legitimate client (a buggy uploader) can also trip it.

**Fix:**

Stream the upload into a bounded buffer, abort early once the cap is exceeded.
A tiny helper avoids per-handler duplication:

```python
async def read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read *file* in 64 KB chunks, raise FILE_TOO_LARGE before exceeding max_bytes."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise DomainValidationError(
                code="FILE_TOO_LARGE",
                message=f"Upload exceeds the {max_bytes // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)
```

Each upload route then calls `read_capped(file, _MAX_BYTES)` instead of
`file.read()`. The handler's bookkeeping (extension allowlist, SVG scrubbing,
on-disk write) is unchanged.

Pair with a defensive `client_max_body_size 5m` for `location /api/v1/users/me/avatar`
and similar in `nginx.conf` (the 50 MB global cap is meant for raw XML / corpus
uploads on `/api/v1/collections/{slug}/upload`).

---

### 3. Forge `base_url` validators allow loopback / link-local / private-IP hosts — SSRF + PAT exfiltration risk — **LOW**

**Files:**
- [backend/app/plugins/codeberg_integration/schemas.py](backend/app/plugins/codeberg_integration/schemas.py)
- [backend/app/plugins/github_integration/schemas.py](backend/app/plugins/github_integration/schemas.py)
- [backend/app/plugins/gitlab_integration/schemas.py](backend/app/plugins/gitlab_integration/schemas.py)
- [backend/app/plugins/dataverse_integration/schemas.py](backend/app/plugins/dataverse_integration/schemas.py)

**Description:**

Each forge plugin accepts a per-link / global `base_url`. The validator only
checks the URL scheme:

```python
@field_validator("base_url")
@classmethod
def _strip_trailing_slash(cls, v: str) -> str:
    v = v.strip()
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("base_url must start with http:// or https://")
    return v.rstrip("/")
```

There is no host blocklist, so the following are all accepted:

| Submitted `base_url` | Effect when the plugin authenticates |
|---|---|
| `http://169.254.169.254/` | AWS / GCP metadata reachable; PAT sent in `Authorization` header to the metadata service |
| `http://localhost:8080/` | Reaches the in-cluster eXist-db; PAT sent there |
| `http://aracne2-postgres-1:5432/` | Reaches the in-cluster Postgres |
| `http://10.0.0.1/` | Probes private network |

The Codeberg / GitHub / GitLab adapters then send the global PAT (or per-link
override) in `Authorization: token <PAT>` against the configured base URL,
turning a mis-configured (or maliciously configured) link into a credential
leak.

**In-app impact:**

The endpoints that write `base_url` require `EditorInChief+` (per-link) or
`Admin` (global). In the closed-audience trust model both are vetted humans, so
the realistic vector is a *mistake* (admin pastes the wrong URL) rather than
*attack*. The realistic blast radius is therefore limited to leaking the PAT
into the operator's own logs / a typo'd internal service. Severity stays LOW
under the current model — but the cost of the fix is small and rules out the
hostile-admin path entirely.

**Fix:**

Resolve the host of `base_url` and reject any address in a private / loopback /
link-local / multicast / reserved range, both at write time (Pydantic validator)
and at use time (defence in depth):

```python
import ipaddress, socket
from urllib.parse import urlparse

def _assert_public_host(url: str) -> None:
    host = urlparse(url).hostname or ""
    if not host:
        raise ValueError("base_url has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"base_url host could not be resolved: {exc}") from None
    for fam, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local \
           or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError(f"base_url resolves to a non-routable address: {ip}")
```

Apply in the forge schemas' `field_validator("base_url")` and re-check at the
HTTP-client call site (DNS rebinding mitigation). The `*.localdomain.example`
test patterns in the existing tests still resolve to public-suffix names, so the
test suite isn't affected.

The Zenodo plugin already restricts `base_url` to the sandbox/production enum
and is not affected.

---

### 4. `GET /collections/{slug}/documents/{filename}/source` does not validate `filename` — **LOW**

**File:** [backend/app/routers/public_view.py:180-205](backend/app/routers/public_view.py#L180-L205)

**Description:**

The new public TEI download endpoint (`608255f`) interpolates the URL path
parameter `filename` directly into two sinks:

```python
xml_bytes = await existdb_client.get_document(slug, filename)
return Response(
    content=xml_bytes,
    media_type="application/xml",
    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
)
```

Two concerns:

1. **`existdb_client.get_document(slug, filename)`** builds the URL via
   `_rest_url(*segments)` which `.strip('/')`s each segment but does **not**
   URL-encode. A `filename` value containing `..` or other special characters is
   forwarded to eXist-db, relying on eXist-db to reject the traversal. The
   mediaroot endpoint (`public_serve_document_media`) already does this
   correctly via `media_svc.get_media_path()` → `_validate_doc_filename()` +
   `sanitize_filename()` + `_assert_contained()`. The TEI source endpoint should
   apply the same `_validate_doc_filename()` before calling eXist.

2. **Header injection in `Content-Disposition`** — the f-string wraps `filename`
   in double quotes without escaping. If `filename` contains a literal `"`
   (URL-encoded `%22`), the header becomes
   `attachment; filename="evil";injected="value"`. Starlette / FastAPI strip
   CRLF from path values so HTTP-response splitting is not reachable, but a
   crafted filename can still confuse downstream proxies / browsers reading the
   header.

**In-app impact:**

The endpoint is unauthenticated and gated only by collection-published-and-public.
Path traversal severity depends on eXist-db's URL handler — known eXist
versions normalise `..` segments at the REST layer, so a deep traversal is
unlikely. The header-injection vector is mostly cosmetic.

**Fix:**

```python
from app.services.media import _validate_doc_filename

@router.get("/collections/{slug}/documents/{filename}/source")
async def public_document_source(slug: str, filename: str, db):
    _validate_doc_filename(filename)              # ← new guard
    await get_public_collection(db, slug)
    xml_bytes = await existdb_client.get_document(slug, filename)
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
```

`_validate_doc_filename` already enforces the documented filename grammar
(letters, digits, `.`, `_`, `-`); it raises `DomainValidationError`
(→ `400 INVALID_FILENAME`) for anything else, which is the right answer for
this endpoint.

Apply the same guard to any sibling endpoint that interpolates `filename` into
a URL or a header (`download_pdf`, audit if any).

---

## Confirmed clean — new features

| Area | Verdict |
|---|---|
| Authority-lookup family (12 plugins) | Each `/search` endpoint requires auth (≥ User), is rate-limited (`30/min`), caps `q` at 200 chars and ≥ 2 chars, and forwards to a hardcoded upstream. No SSRF surface from user input |
| Trismegistos `POST /resolve` | Body schema enforces `kind` enum + `identifier` ≤ 200 chars |
| CrossRef `GET /lookup` | EditorInChief+, rate-limited, `doi` length-bounded |
| Plugin auto-cabling registry contract | `capabilities` and `ui_descriptor` flow PluginMeta → DB → API → SPA registry; tests in `test_plugin_capabilities.py` cover insert, reboot-overwrite, default empty state, and frontend ↔ backend coherence |
| Plugin hot-mount / hot-unmount | `POST /plugins/{name}/{activate,deactivate}` requires `Admin`; route mutation tracked per-plugin so unmount removes only that plugin's routes |
| User avatar — extension allowlist | Only `.jpg .jpeg .png .gif .webp .avif` accepted; SVG **explicitly excluded** with a code comment citing XSS as the reason |
| User avatar — file naming | Path derived from `user.id` (UUID), not from user-supplied filename → no path traversal |
| User Markdown bio rendering | `renderBio()` HTML-escapes input first then injects only `<strong>`, `<em>`, `<u>`, `<br>`. Bio is shown only on the owner's own profile (no cross-user surface) |
| Website SVG upload scrubbing | `_sanitize_svg()` parses with `defusedxml` (XXE-proof), strips forbidden tags, `on*` attributes, `javascript:` and `data:` hrefs |
| Website custom CSS / custom JS | Designer role explicitly trusted to inject CSS / JS into rendered websites. `</style>` / `</script>` stripped at the boundary so the injection cannot escape its container; CSP applies to public sites |
| Wikidata hover preview | Outbound fetch uses Wikidata's public REST API; rendered values pass through Vue's text interpolation (no `v-html`) |
| `home_intro_html` media references | `media://` refs are rewritten via `useHomepageMedia` to a same-origin URL; no open-redirect surface |
| Bibliography filename linkification | Link target built server-side from validated `slug` + filename; client renders `<router-link>` so no `v-html` sink |
| `/sites/<slug>` URL flattening | Removed `/api/v1` prefix exposes the same handlers behind a different path; `_check_site_access()` still enforces the same access guard |
| Public-search iframe escape | Uses `target="_top"` only on result anchors so admin → simple/advanced toggles stay inside the iframe |
| i18n `@<word>` escaping (`f1cc7e3`) | Pre-existing vue-i18n parser bug fix — no security impact, listed for completeness |
| Plugin secrets logging | Outbound clients (Zenodo, IA, Codeberg, GitHub, GitLab, Dataverse) — none log the PAT / API token; structlog calls only carry plugin id + slug + status code |
| `SENSITIVE_KEYS` coverage | New deposit/integration tokens (`zenodo_api_token`, `internet_archive_*`, `codeberg_integration_pat`, `github_integration_pat`, `gitlab_integration_pat`, `dataverse_api_token`, `zotero_api_key`) are all listed → Fernet-encrypted at rest, masked in API responses |

---

## Deferred (carried over)

| Item | Reason |
|---|---|
| `vite` / `esbuild` / `vitest` / `postcss` / `follow-redirects` npm moderate | Dev-tooling chain only; no production exposure |
| Magic-byte validation for media uploads | No execution path; extension allowlist + SVG scrubbing adequate |
| Settings / plugin events in audit log | Out of scope; tracked separately |
| `pip` upgrade inside container | Package manager, not application code |

---

## Resolution summary

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | LOW | `home_intro_html` accepted as raw HTML, rendered via `v-html` | Open |
| 2 | LOW-MEDIUM | Upload endpoints buffer full body before size check | Open |
| 3 | LOW | Forge `base_url` allows private / loopback hosts | Open |
| 4 | LOW | Public TEI source download — `filename` not validated | Open |

Recommended order of operations: **4 → 1 → 2 → 3** (smallest surgical fix to
largest behavioural change). All four fit a single defensive-hardening commit.
