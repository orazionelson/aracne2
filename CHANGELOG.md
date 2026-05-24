# Changelog

All notable changes to Aracne2 are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases prior to this file (`v1.0.0`, `v1.0.1`) are not retroactively
documented; see the corresponding git tags for the historical commit log.

## [Unreleased]

### Security

- **Dependency bumps closing 12 Dependabot alerts (Phase 1).** Sixteen of
  the eighteen open Dependabot alerts as of 2026-05-20 concentrated in
  three packages and all sat within existing semver ranges; bumping them
  required no breaking changes and no API surface changes for Aracne2
  consumers.
  - `axios` `1.15.0 → 1.16.1` (within the project's `^1.15.0` range)
    closes 14 alerts including 4 high-severity prototype-pollution and
    header-injection gadgets (GHSA-pf86-5x62-jrwf, GHSA-6chq-wfr3-2hj9,
    GHSA-q8qp-cvcw-x6jj, GHSA-pmwg-cvhr-8vh7).
  - `follow-redirects` `1.15.11 → 1.16.0` (transitive of axios) closes
    GHSA-r4q5-vmmm-2653 (auth-header leak on cross-domain redirect).
  - `js-cookie` `3.0.5 → 3.0.7` (transitive of `@vue/test-utils` → `js-beautify`,
    test-only) closes GHSA-qjx8-664m-686j (per-instance prototype hijack).
  - `python-multipart` `0.0.26 → 0.0.27` (backend) closes
    GHSA-pp6c-gr5w-3c5g (DoS via unbounded multipart part headers).
  The remaining six alerts all sit in the `vite` cluster (`vite`, `esbuild`,
  `vitest`, `@vitest/coverage-v8`, `vite-node`), all moderate, all dev-scope.
  Their fix requires a `vite 5 → 6` major bump and is deferred to a
  separate task with build-time verification.

### Added

- **Self-service password change** in the user profile view ([`c1fdd50`]).
  Authenticated users can update their own password from the Profile page
  without admin intervention. The backend endpoint is rate-limited at the
  existing `STRICT_LIMIT` tier.

### Compatibility

- **Validated on Oracle Linux 10 (Red Hat family).** First successful
  end-to-end install on OL10 with Docker 29 + containerd snapshotter on
  ext4/LVM. The four fixes below were uncovered during that install and
  collectively make Aracne2 deployable on RHEL-family hosts without
  Docker-engine downgrades or kernel tuning.

### Fixed

- **Avatar upload not reflected without a hard reload — backend payload
  was missing the field.** `_build_response` and `_build_response_from_loaded`
  in `backend/app/services/users.py` constructed the `UserResponse`
  without `avatar_url` and `bio`; both fields are declared optional with
  a `None` default on the schema, so Pydantic silently filled them in as
  null. Every endpoint going through these helpers — including
  `POST /users/me/avatar` and `DELETE /users/me/avatar` — therefore
  returned `avatar_url: null` regardless of what was actually persisted.
  The page-load path uses a different schema (`UserMeResponse`, built by
  hand in `routers/auth.py`) which DOES include the field, which is why
  a manual browser reload "fixed" the avatar — and why the bug went
  unnoticed: the only observable symptom was an upload-then-stale UI.
  Pass `avatar_url=user.avatar_url` and `bio=user.bio` explicitly in
  both helpers. The earlier frontend cache-bust (`avatarVersion`
  counter + `?v=<n>` query string in `UserAvatar`) is complementary and
  remains in place — it handles the second-upload case where the URL
  itself is identical before and after.
- **Silent error swallowing in auth forms** — `LoginView` and
  `ConfirmPasswordResetView` collapsed every exception (network, 5xx,
  rate-limit, JS error from an interceptor) into the same domain-specific
  message ("Invalid credentials" / "Invalid or expired link"), with no
  `console.error`. That made [`d4c2cfd`] (and any future pre-fetch JS
  failure) look like a credentials mistake and forced blind debugging.
  Both forms now keep the generic message only on a backend `401`
  (preserving information-leak prevention) and route every other failure
  to `console.error` plus a new `common.unexpected_error` UI string.
- **Backend writable mountpoints under Docker 29 / containerd snapshotter** —
  moved `/app/schemas` and `/app/media` from the source bind-mount to
  dedicated named volumes ([`75f34bb`]), and pre-created both mountpoints
  in the backend image with `appuser` ownership ([`cc24e7f`]). Together
  these resolve two unrelated container-level blockers (`EROFS` then
  `EACCES`) observed on Docker 29 + containerd snapshotter on a custom
  ext4/LVM mount, and align development with the named-volume pattern
  already documented for production in `backend/app/config.py`.
- **Frontend login on plain-HTTP LAN deployments** — `crypto.randomUUID()`
  is gated to secure contexts (HTTPS or localhost) by the W3C Web Crypto
  spec and is `undefined` on plain HTTP non-localhost addresses (intranet
  IPs). The axios request interceptor used it for `X-Request-ID` and
  threw `TypeError` before any HTTP call was issued — the developer saw
  no network entry, no console error, and no backend log: a perfectly
  silent block. Introduced `makeUuidV4()` in `frontend/src/utils/uuid.ts`
  with a `crypto.getRandomValues()` fallback (which is **not** gated by
  secure context); the five `crypto.randomUUID()` call sites now use it
  ([`d4c2cfd`]).
- **Fresh-clone frontend build** — `npm ci` failed on every clean clone
  because `package-lock.json` lagged behind a `package.json` bump from
  the 2026-05-03 security review. Regenerated the lockfile under
  `node:20-alpine` (the same image used by `frontend/Dockerfile`) so the
  resolution matches what runs in the build. Diff is surgical: `postcss`
  `8.5.8 → 8.5.15` and transitive `nanoid` `3.3.11 → 3.3.12`, no other
  bumps ([`aa6592d`]).

### Internal

- `.gitignore` now covers all six backend runtime data directories
  (`schemas/`, `media/`, `documents_media/`, `sites/`, `search-pages/`,
  `backups/`) and `*.log` files, reducing untracked noise in `git status`
  for any directory that has run the stack ([`b4b70e5`]).

[Unreleased]: https://github.com/orazionelson/aracne2/compare/v1.0.1...HEAD
[`c1fdd50`]: https://github.com/orazionelson/aracne2/commit/c1fdd50
[`75f34bb`]: https://github.com/orazionelson/aracne2/commit/75f34bb
[`aa6592d`]: https://github.com/orazionelson/aracne2/commit/aa6592d
[`cc24e7f`]: https://github.com/orazionelson/aracne2/commit/cc24e7f
[`d4c2cfd`]: https://github.com/orazionelson/aracne2/commit/d4c2cfd
[`b4b70e5`]: https://github.com/orazionelson/aracne2/commit/b4b70e5
