# Contributing to Aracne2

Aracne2 is currently developed by a single maintainer
([Alfredo Cosco](https://github.com/orazionelson)). The codebase is
public so the digital-humanities community can use it, fork it, and
build on it; contributions back to this repo are welcome but flow
through a deliberate process.

## What kind of contributions are welcome

- **Bug reports** with a clear repro case — open an issue.
- **Documentation fixes** — typos, broken links, unclear sections.
  Open a PR; small docs PRs typically merge same-day.
- **Plugins** — the platform is plugin-modular by design. A new
  authority-lookup, deposit backend, or LOD integration is a clean
  fit for a non-native plugin under
  [`backend/app/plugins/<slug>/`](backend/app/plugins/). See
  [docs/reference/PLUGINS.md](docs/reference/PLUGINS.md) for the
  full plugin contract and
  [docs/reference/NON_NATIVE_PLUGINS.md](docs/reference/NON_NATIVE_PLUGINS.md)
  for the conventions every shipped plugin follows.
- **Bug fixes** — the smaller, the better. Fix one thing per PR.
- **Tests for existing features** that lack coverage.

## What is NOT a good fit (yet)

- **Large refactors of the editorial workflow or the platform's
  data model.** Open an issue first; these touch decisions that
  cascade into every deployment and need a design conversation
  before code.
- **Alternative stacks.** The stack is intentionally fixed
  (Python 3.12 + FastAPI + PostgreSQL + Vue 3 + Tailwind +
  eXist-db). Proposals to swap a layer will be politely declined.
- **Features not driven by an actual editorial use case.**
  Aracne2 grew out of a specific philological practice; speculative
  features without a project behind them tend to add maintenance
  surface without adding value.

## Process

1. **Open an issue first** for anything bigger than a typo. A
   one-paragraph problem statement is usually enough.
2. **Wait for a thumbs-up** before writing code. The maintainer
   may know that the area is in flux, or that a similar PR is
   already open.
3. **Fork + branch + PR.** Branch from `main`. PR target is `main`
   (no separate `develop` / `release` branches).
4. **Tests + lint pass.** Run locally before pushing:
   ```bash
   make test           # backend pytest
   make lint           # ruff + mypy
   cd frontend && npm run typecheck
   ```
5. **Commit messages**: short imperative subject (≤ 70 chars),
   optional body explaining *why*. Multi-line subjects starting
   with `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`,
   `chore(...)` mirror conventional commits but the prefix isn't
   enforced.
6. **One concern per PR.** Mixing a bug fix with a refactor and a
   new feature in the same PR makes review impossible.

## Code conventions

- All comments, docstrings, commit messages, and documentation are
  in **English**.
- Backend: full type hints, async throughout, ORM-only (no raw SQL
  strings in business logic), Pydantic v2 for validation,
  `defusedxml` for any XML parsing. New endpoints declare
  `Depends(require_role(...))` or `Depends(get_current_user)`
  explicitly — no implicit security.
- Frontend: `<script setup lang="ts">`, Pinia for shared state,
  no `any` (use `unknown` + type guards), every user-visible string
  must use `$t('key')` with the key declared in both
  `src/locales/en.json` and `src/locales/it.json`.
- Avoid backwards-compat hacks. Code is changed, not soft-deprecated.

## Reporting security issues

Don't open public issues for vulnerabilities — see
[SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by the
[Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
