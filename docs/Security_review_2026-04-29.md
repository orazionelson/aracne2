# Security Review — 2026-04-29

**Previous review:** `Security_review_2026-04-27.md` (last covered commit: `916931e`)
**Current HEAD on `development`:** `7ea7301`
**Branch:** `development`
**Scope:** Dependabot-driven audit before flipping the repo from
private to public. GitHub reported 1 high + 7 moderate; the
investigation expanded to the Python ecosystem too (Dependabot scans
both `package-lock.json` and `requirements.txt`).

---

## Automated tools

### `npm audit`

Same eight moderates as the previous review (axios was already on
the safe 1.15.0 since 2026-04-16). All eight are dev-tooling
chains — `vite`, `vitest`, `esbuild`, `postcss`, `follow-redirects`,
`@vitest/*`. None production-reachable. Unchanged.

### `pip-audit`

Five Python advisories — none of these were tracked in earlier
reviews because Dependabot wasn't active on the private repo:

| Package | Version | Advisory | Severity | Fix |
|---|---|---|---|---|
| `lxml` | 5.3.0 | CVE-2026-41066 — XXE: default `resolve_entities=True` lets untrusted XML read local files | **HIGH** | 6.1.0 |
| `cryptography` | 46.0.6 | CVE-2026-39892 — buffer overflow in `Hash.update()` on non-contiguous buffers | MED-HIGH | 46.0.7 |
| `python-multipart` | 0.0.22 | CVE-2026-40347 — DoS on crafted multipart preamble/epilogue | MED | 0.0.26 |
| `pyasn1` | 0.4.8 | CVE-2026-30922 — DoS via uncontrolled recursion on deeply nested ASN.1 | MED | 0.6.3 |
| `pytest` | 8.3.4 | CVE-2025-71176 — local DoS via `/tmp/pytest-of-{user}` directories | LOW (dev-only) | 9.0.3 |

---

## Findings

---

### 1. lxml 5.3.0 + default `etree.fromstring(xml_bytes)` on Editor-authored TEI — XXE — **HIGH** ✅ Fixed `<this commit>`

**Files:**
- [backend/app/services/public_view.py:242](backend/app/services/public_view.py#L242)
- [backend/app/services/websites.py:1544](backend/app/services/websites.py#L1544)
- [backend/app/services/websites.py:2334](backend/app/services/websites.py#L2334)

**Description:**

Three rendering paths parsed TEI bytes with `etree.fromstring(xml_bytes)`
without an explicit parser. Each carried a `# noqa: S320 — trusted
eXist-db source` comment, asserting that bytes coming from eXist-db
were trustworthy and therefore the lxml default
`resolve_entities=True` was acceptable.

The assertion is **wrong** in the platform's threat model. Editor
role can write arbitrary TEI to eXist-db with their own role; eXist
is not a trust boundary against XXE. A malicious Editor uploads:

```xml
<?xml version="1.0"?>
<!DOCTYPE TEI [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><p>&xxe;</p></body></text>
</TEI>
```

When the public renderer calls `_render_xml_to_html(xml_bytes)` on
this document, lxml resolves `&xxe;` at parse time and the file
content lands in the public HTML output. Same vector for the
website generator's `_render_xml_to_html` and the page-level
`<surface>` extractor at `websites.py:1544`.

CVE-2026-41066 is the same class of issue at the lxml package
level — the upstream patch in 6.1.0 flips the default to
`resolve_entities=False`. Bumping lxml alone would fix the immediate
vulnerability, but defence-in-depth says the platform should pass
an explicit safe parser regardless of upstream defaults; that way
a future downgrade or a different rendering path doesn't reintroduce
the gap.

**Fix:**

Pass an explicit hardened parser at every call site:

```python
_safe_parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
)
xml_doc = etree.fromstring(xml_bytes, parser=_safe_parser)
```

Pattern mirrors the existing `_safe_xml_parser` in
[backend/app/services/schemas.py:64](backend/app/services/schemas.py#L64).
Plus bump `lxml` 5.3.0 → 6.1.0 in `requirements.txt` to close the
underlying CVE.

**In-app impact (pre-fix):**

An Editor with write access to any collection could exfiltrate
arbitrary readable files from the backend container's filesystem —
including `/etc/passwd`, the `app/` source tree, and most
significantly, environment variables that some operators write to
files inside the container. Exfiltration channel: the rendered
public HTML or the website static export. Severity HIGH because
it grants Editor → arbitrary-file-read across a role boundary.

---

### 2. `cryptography` 46.0.6 buffer-overflow CVE — **MED-HIGH** ✅ Fixed `<this commit>`

**File:** [backend/requirements.txt](backend/requirements.txt)

**Description:**

CVE-2026-39892: `Hash.update()` and similar primitives accept
non-contiguous Python buffers; on certain combinations of arch +
input shape this triggers a buffer overflow in the C extension.

Aracne2 doesn't call `Hash.update()` on user-controlled
non-contiguous buffers directly, but the package is reachable from:
- Fernet encryption / decryption in
  [`app/core/encryption.py`](backend/app/core/encryption.py)
- `python-jose[cryptography]` for JWT signing / verification

A targeted exploit would need a specific buffer shape we don't
construct, so the *exploitable* surface is narrow. Bumping the
package is trivial — patch-version bump 46.0.6 → 46.0.7.

**Fix:** version bump in `requirements.txt`.

---

### 3. `python-multipart` 0.0.22 — DoS on crafted multipart bodies — **MED** ✅ Fixed `<this commit>`

**File:** [backend/requirements.txt](backend/requirements.txt)

**Description:**

CVE-2026-40347: an authenticated client posting a crafted
`multipart/form-data` body with an oversized preamble or epilogue
forces the parser into a slow path. Per the upstream advisory, the
attack is "single-request CPU exhaustion" — not memory.

Aracne2's upload routes (avatar, logo, CSS, homepage media,
website media, schema upload) all pass through this parser. nginx
caps the body at 50 MB; the per-handler read-cap helper from the
2026-04-27 review further bounds memory. CPU is the residual
vector.

**Fix:** version bump 0.0.22 → 0.0.26.

---

### 4. `pyasn1` 0.4.8 — DoS via deeply-nested ASN.1 — **MED** ⏸ Risk-accepted

**File:** [backend/requirements.txt](backend/requirements.txt)

**Description:**

CVE-2026-30922. Uncontrolled recursion when decoding crafted ASN.1
with deeply-nested structures. `pyasn1` is a transitive dep
(pulled by `python-jose[cryptography]`); the concrete attack
surface is whoever feeds the JWT verifier or the X.509 cert parser.

Aracne2 verifies JWT issued **by itself**, against tokens it
signed seconds earlier — there's no untrusted-issuer flow that
would let an attacker plant a malicious ASN.1 payload. So the
realistic exploit requires the operator to wire in an external
identity provider, which we don't ship today.

**Why not bumped:** `python-jose 3.4.0` pins `pyasn1<0.5.0`, so
adding `pyasn1==0.6.3` directly in `requirements.txt` triggered a
`ResolutionImpossible` at `pip install`. Two paths to actually
ship the fix: (a) wait for `python-jose` to relax its pin, (b)
migrate the JWT layer from `python-jose` to `PyJWT` (which uses
`cryptography` directly, no `pyasn1` dependency).

Path (b) is the right long-term answer — `python-jose` has been
in low-maintenance mode for years — but it's a code change
(JWT signing / verification helpers + tests) that doesn't fit
the public-flip prep.

**Decision:** accept the residual MED risk on the basis that:
- the only ASN.1 input the platform decodes is its own JWTs;
- attacker-controlled JWTs are rejected by signature verification
  *before* the payload is decoded;
- bumping requires a non-trivial library swap.

Tracked in [DEFERRED.md](DEFERRED.md) with the trigger to revisit
once the JWT-layer migration is on the work list.

---

### 5. `pytest` 8.3.4 — local DoS on `/tmp/pytest-of-{user}` — **LOW (dev-only)** ⏸ Deferred

**File:** [backend/requirements.txt](backend/requirements.txt)

**Description:**

CVE-2025-71176. UNIX-only. `pytest` creates `/tmp/pytest-of-{user}`
as a predictable directory; another local user can race the
creation to inflict a DoS or escalate via symlink games.

This affects test-runs only. Production deployments of Aracne2 do
not run `pytest`. Bumping `pytest` 8 → 9 is a major-version jump
that may break `pytest-asyncio==0.24.0` and `pytest-cov==6.0.0`
plugin compatibility — confirmed via release notes that several
plugin APIs changed.

**Decision:** defer until `pytest-asyncio` and `pytest-cov` ship
stable 9-compatible versions, then bump all three together. Track
in `DEFERRED.md`.

---

## Confirmed clean — pre-publish audit

| Area | Verdict |
|---|---|
| `npm audit` | Unchanged 8 moderate, all dev-tooling, none production-reachable |
| Direct hardcoded secrets | None tracked; only placeholder `changeme_*` defaults in `.env.example` |
| Personal data in code | Only `alfredo` in path strings inside `CLAUDE.md` (now untracked); zero in tracked files |
| Email addresses | Only fake / fixture (`a@b.com`, `scaffold@test.com`) and explicit placeholders (`ops@yourorg.example`); no real PII |
| Git history | Retains MaRa/Aracne lineage, no embarrassing or sensitive content; SHA references in older Security_review_*.md remain valid (no history rewrite) |
| `phases/` and `CLAUDE.md` | Removed in commit `2fc4842` from the tracked tree; history retains them, but content is just internal process documentation |

---

## Resolution summary

Fixes 1–4 land on `development` in this commit. Fix 5 is deferred.

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | HIGH | lxml XXE on Editor-authored TEI rendering paths | ✅ Fixed (this commit) |
| 2 | MED-HIGH | `cryptography` 46.0.6 buffer overflow | ✅ Fixed (this commit) |
| 3 | MED | `python-multipart` 0.0.22 multipart DoS | ✅ Fixed (this commit) |
| 4 | MED | `pyasn1` 0.4.8 ASN.1 DoS | ⏸ Risk-accepted — blocked by `python-jose 3.4` pin; revisit with PyJWT migration. Tracked in DEFERRED.md |
| 5 | LOW | `pytest` 8.3.4 local DoS | ⏸ Deferred — track in DEFERRED.md, bump with `pytest-asyncio` / `pytest-cov` 9-compatible releases |

Once this commit lands and the next test-directory pull confirms
the test suite still passes, the repo is clean for the public flip.
