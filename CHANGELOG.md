# Changelog

All notable changes to Aracne2 are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases prior to this file (`v1.0.0`, `v1.0.1`) are not retroactively
documented; see the corresponding git tags for the historical commit log.

## [Unreleased]

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
