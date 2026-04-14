# Security Review — 2026-04-14

**Previous review:** `Security_review_2026-04-11.md` (last covered commit: `eebbaac`)  
**Current HEAD:** `57d0c26`  
**Branch:** `main`  
**Scope:** Differential review — all commits since `eebbaac` (62 commits)  
**New features under review:** Media API (Phases 1–4), Direct Publish workflow,
GeoNames/VIAF proxy endpoints, Facsimile management, Editor improvements.

---

## Automated tools

### `pip-audit`

No new vulnerabilities since `eebbaac`. No Python dependency changes in the 62 commits.

### `npm audit`

No frontend dependency changes in the 62 commits. The deferred `vite`/`esbuild`
upgrade remains out of scope (dev server only, no production impact).

---

## Findings

---

### 1. ZIP batch upload skips XXE validation — **CRITICAL**

**File:** [backend/app/services/xmldb.py](backend/app/services/xmldb.py#L887-L888)  
**Lines:** 887–888 (ZIP path) vs. 699–703 (single-file path)

**Description:**

The single-document upload guards against XXE and malformed XML before writing to
eXist-db:

```python
# upload_document — line 699
try:
    _safe_xml.fromstring(xml_bytes)   # defusedxml — blocks XXE, validates well-formedness
except Exception as exc:
    raise DomainValidationError("INVALID_XML", ...)
await existdb.put_document(col.slug, filename, xml_bytes)
```

The ZIP batch upload reads members and writes them directly without this check:

```python
# upload_zip_batch — line 887
xml_bytes = zf.read(member.filename)
await existdb.put_document(col.slug, basename, xml_bytes)   # no XXE check
```

**Impact:**

An authenticated Editor+ user can upload a ZIP archive containing XML documents with
DOCTYPE declarations and external entity references. The malicious documents are
stored in eXist-db without validation. This breaks the "trusted eXist-db source"
invariant relied upon by downstream lxml parsing in `websites.py` (lines 1114,
1759) and `public_view.py` (line 166). When a website build or dynamic rendering
call processes the stored document, `etree.fromstring()` may resolve the XXE
payload — enabling local file read or server-side request forgery.

**Fix:**

Add the defusedxml well-formedness check inside the per-member loop in
`upload_zip_batch`, immediately after `zf.read()`:

```python
xml_bytes = zf.read(member.filename)
try:
    _safe_xml.fromstring(xml_bytes)
except Exception as exc:
    errors.append(ZipUploadError(filename=basename, error=f"Invalid XML: {exc}"))
    continue
await existdb.put_document(col.slug, basename, xml_bytes)
```

---

### 2. `doc_filename` path traversal in media service — **HIGH**

**Files:**  
- [backend/app/services/media.py](backend/app/services/media.py) — `list_media`, `save_media`, `delete_media`, `get_media_path`  
- [backend/app/routers/media.py](backend/app/routers/media.py)  
- [backend/app/routers/public_view.py](backend/app/routers/public_view.py#L52-L68)

**Description:**

The `doc_filename` URL path parameter is passed directly to the media service
without validation. The document filename validator `_validate_filename()` (used
in `xmldb.py` line 84) enforces `^[a-zA-Z0-9][a-zA-Z0-9._\-]*\.xml$`, which
would block traversal patterns, but it is never called for `doc_filename` in the
media layer.

An attacker can pass `%2E%2E` (URL-encoded `..`) as `doc_filename`. Starlette
decodes this to the literal string `..` before routing, which FastAPI then supplies
to the handler. The result:

```
_media_dir("my-col", "..") == documents_media_root / "my-col" / ".."
   (resolved) == documents_media_root
```

**`_assert_contained` does not catch this** because the resolved path
`documents_media_root/image.jpg` IS still relative to `documents_media_root`. The
guard only checks the root boundary, not the collection subdirectory boundary.

**`list_media` has no `_assert_contained` call at all** (lines 118–141 of
`media.py`). It iterates the resolved directory without any containment check.

**Specific impacts:**

| Endpoint | Vector | Impact |
|---|---|---|
| `GET .../documents/%2E%2E/media` [E+] | `doc_filename = ".."` | Lists entire `documents_media_root` — directory structure of all collections disclosed to any Editor |
| `POST .../documents/%2E%2E/media` [E+] | same | Saves file to `documents_media_root/safe_name` instead of the expected collection subdirectory |
| `DELETE .../documents/%2E%2E/media/{filename}` [E+] | same | Deletes file at `documents_media_root/filename` (if it exists) |
| `GET /api/v1/public/collections/{slug}/documents/%2E%2E/media/{filename}` [pub] | same | Serves a file from `documents_media_root/filename` — unauthenticated. If such a file exists (e.g. placed via the authenticated write path), a public user can access it without collection-level ACL. |

**Fix:**

Apply `_validate_filename(doc_filename)` in the media service (or at router
boundary) for every operation. `_validate_filename` already exists in `xmldb.py`
and rejects any string that contains `..`, `.`, or lacks the `.xml` suffix. Export
it (or duplicate the regex as a helper in `services/media.py`) and call it before
constructing `_media_dir()`.

Additionally, add `_assert_contained` to `list_media`:

```python
async def list_media(collection_slug: str, doc_filename: str) -> list[MediaItem]:
    _validate_filename(doc_filename)          # <-- add this
    media_dir = _media_dir(collection_slug, doc_filename)
    _assert_contained(media_dir)              # <-- add this
    ...
```

---

### 3. ZIP bomb protection based on declared size — **MEDIUM**

**File:** [backend/app/services/xmldb.py](backend/app/services/xmldb.py#L867-L873)  
**Lines:** 867–873

**Description:**

The zip-bomb guard checks `member.file_size`, which is the *declared* uncompressed
size stored in the ZIP central directory header. A malicious ZIP can declare
`file_size = 0` for all members while containing highly-compressed data that
expands to gigabytes. When `zf.read(member.filename)` runs, Python decompresses
the full payload into memory before the size is checked.

```python
total_extracted += member.file_size   # declared size — can be falsified
if total_extracted > max_extracted_mb * 1024 * 1024:
    raise DomainValidationError(...)

xml_bytes = zf.read(member.filename)  # actual decompression — no streaming limit
```

**Impact:** Denial of service via memory exhaustion. Requires Editor+ authentication.

**Fix:**

Stream the decompression with a real-time byte counter, rejecting when the
actual bytes read exceed the limit:

```python
import io

buf = io.BytesIO()
with zf.open(member.filename) as f:
    while True:
        chunk = f.read(65536)
        if not chunk:
            break
        buf.write(chunk)
        if buf.tell() > max_extracted_mb * 1024 * 1024:
            raise DomainValidationError(
                "ZIP_EXTRACTED_TOO_LARGE",
                f"A single extracted file exceeds the {max_extracted_mb} MB limit",
            )
xml_bytes = buf.getvalue()
```

Remove the `total_extracted += member.file_size` pre-check (or keep it as a fast
first-pass only, documented as untrusted).

---

### 4. Missing rate limiting on GeoNames and VIAF proxy endpoints — **MEDIUM**

**Files:**  
- [backend/app/routers/geonames.py](backend/app/routers/geonames.py#L32)  
- [backend/app/routers/viaf.py](backend/app/routers/viaf.py#L23)

**Description:**

Both endpoints fall under the default `GLOBAL_LIMIT` (200 requests/minute per
IP). Neither applies the `@limiter.limit(STRICT_LIMIT)` decorator.

GeoNames free accounts have a daily cap of 1 000 API calls. A single authenticated
user (any role, `min_role="User"`) could fire 200 requests per minute, exhausting
the daily quota in 5 minutes and making the autocomplete feature unavailable for
all other users for the remainder of the day.

**Fix:**

Apply a specific limit to both endpoints. A reasonable cap for typeahead proxies
is 30 requests/minute per IP:

```python
from app.middleware.rate_limiter import limiter

@router.get("/search")
@limiter.limit("30/minute")
async def geonames_search(request: Request, ...) -> ...:
```

Note: `slowapi`'s `@limiter.limit()` requires `request: Request` as a named
parameter in the function signature.

---

### 5. Media upload/delete not written to `audit_log` — **MEDIUM**

**File:** [backend/app/routers/media.py](backend/app/routers/media.py#L100-L108)  
**Lines:** 100–108 (upload), 126–132 (delete)

**Description:**

Both `upload_document_media` and `delete_document_media` log to structlog only:

```python
logger.info("media_uploaded", collection=col.slug, doc=doc_filename,
            filename=item.filename, size=item.size, actor=current_user.username)
```

No entry is written to the `audit_log` table. The previous review (item 16) noted
that document uploads ARE audited via `_audit(db, "document.uploaded", ...)` in
`xmldb.py`. Media operations — which modify a document's associated filesystem
artefacts — have the same sensitivity and should be auditable from the admin
interface.

Structlog output is ephemeral (rotated container logs). The audit table is
queryable and persistent.

**Fix:**

Import `_audit` from `app.services.xmldb` and call it after each operation:

```python
from app.services.xmldb import _audit

# in upload_document_media, after media_svc.save_media():
_audit(db, "media.uploaded", current_user, col,
       {"doc": doc_filename, "filename": item.filename, "size": item.size})

# in delete_document_media, after media_svc.delete_media():
_audit(db, "media.deleted", current_user, col,
       {"doc": doc_filename, "filename": filename})
```

---

### 6. GeoNames and VIAF log raw user queries — **LOW**

**Files:**  
- [backend/app/routers/geonames.py](backend/app/routers/geonames.py#L59)  
- [backend/app/routers/viaf.py](backend/app/routers/viaf.py#L35)

**Description:**

Both endpoints log the raw search string at `INFO` level:

```python
logger.info("geonames_search", q=q, status=resp.status_code)
logger.info("viaf_autosuggest", query=query, status=resp.status_code, url=str(resp.url))
```

VIAF is an authority search for person names. GeoNames returns place names.
Search queries may constitute PII (e.g. an editor searching for a specific
author's name reveals their editorial activity). CLAUDE.md §Security requires
that structlog never log identifiable user data beyond metadata.

**Fix:**

Remove the raw query from INFO-level log entries. Retain it at DEBUG level
(development only) or replace with the result count:

```python
logger.info("geonames_search_ok", count=len(places), status=resp.status_code)
```

---

### 7. Notification string in `direct_publish_collection` in Italian — **LOW (code quality)**

**File:** [backend/app/services/xmldb.py](backend/app/services/xmldb.py#L618)  
**Line:** 618

```python
f"{_actor_label(actor)} ha pubblicato direttamente: {col.title}"
```

CLAUDE.md requires all code strings (including error messages and notification
text generated in Python) to be in English. This is the only Italian string
found in backend Python code in the new commits.

**Fix:**

```python
f"{_actor_label(actor)} has directly published: {col.title}"
```

---

## Confirmed clean — new features

| Area | Verdict |
|---|---|
| Direct Publish ACL | Clean — `_eic` dependency + `_assert_eic(role)` double-check; audit logged at `collection.direct_published`; `ON_COLLECTION_PUBLISHED` hook emitted |
| GeoNames SSRF | Not applicable — target URL is hardcoded; user input reaches the external API only as a query string parameter via httpx (auto-encoded) |
| VIAF SSRF | Same as GeoNames |
| GeoNames/VIAF auth | `require_role(min_role="User")` enforced on both |
| OAI-PMH XML | stdlib `ET` used for building only; `defusedET.fromstring()` used for all parsing — correct split |
| ZIP filename validation | `_validate_filename(basename)` applied to each ZIP member before upload |
| Media extension allowlist | `.jpg .jpeg .png .webp .tif .tiff` enforced at extension and Content-Type levels |
| Media size limit | Configurable via `system_setting.media_max_upload_size_mb` (fallback 50 MB); enforced by reading `max_bytes + 1` |
| Media path containment | `_assert_contained()` via `Path.resolve().relative_to(root)` present in `save_media`, `delete_media`, `get_media_path` — **sufficient once issue 2 is fixed** |
| `sanitize_filename()` | Unicode normalization → basename extraction → safe-char filter → strip leading dots — adequate |
| lxml in `websites.py` / `public_view.py` | "Trusted eXist-db source" argument is valid **once issue 1 is fixed** (ZIP upload XXE gap closed) |
| Media ACL | `_assert_write_access()` enforced on upload and delete; `_assert_read_access()` on list and serve |

---

## Deferred (carried over)

| Item | Reason |
|---|---|
| `vite`/`esbuild` npm upgrade | Breaking change (Vite 8); dev server only |
| `pip` upgrade inside container | Package manager, not application code |
| Settings / plugin events in audit log | Out of scope for this review |
| Magic byte / file-signature validation for media uploads | No execution path; files are served with extension-derived MIME type, never executed by the server. Current extension + Content-Type double-check is adequate for the threat model. If storage is ever shared with a web server that executes scripts, revisit. |

---

## Priority fix order

1. **[CRITICAL] Issue 1** — Add `_safe_xml.fromstring()` to ZIP batch upload
2. **[HIGH] Issue 2** — Apply `_validate_filename(doc_filename)` + `_assert_contained` in `list_media`
3. **[MEDIUM] Issue 3** — Switch ZIP decompression to streaming with real-time size cap
4. **[MEDIUM] Issue 4** — Add `@limiter.limit("30/minute")` to GeoNames and VIAF
5. **[MEDIUM] Issue 5** — Add `_audit()` calls in media upload and delete
6. **[LOW] Issues 6–7** — Log cleanup and Italian string fix
