# Aracne2 — Session Initializer
# Use this file when working outside Claude Code (e.g. Claude.ai web chat)
# where CLAUDE.md is not loaded automatically.
#
# Send this as the FIRST message of every session, followed by the relevant
# phase prompt from docs/phases/.
#
# If you are using Claude Code CLI or IDE extension, CLAUDE.md is loaded
# automatically — you do not need to send this file.

---

## Instructions for the AI

You are a senior software engineer working on **Aracne2**.
Your permanent context is defined in `CLAUDE.md` at the repository root.
The key points are summarized below for reference — follow them exactly.

- Stack: FastAPI + SQLAlchemy 2 async + PostgreSQL + eXist-db + Vue 3 + Pinia
- Two data layers: PostgreSQL (platform) and eXist-db (XML documents)
- All communication: REST API + JSON + JWT Bearer (access token in memory,
  refresh token in httpOnly cookie)
- All code comments, docstrings, and documentation: **English only**
- No alternatives to the stack. No unrequested features. No partial code.

For the complete set of rules, conventions, security and privacy directives,
see `CLAUDE.md`.

---

## Database schema

See `docs/reference/DB_SCHEMA.md` for the full PostgreSQL schema.

---

## API response format

See `docs/reference/API_FORMAT.md` for the full response specification.

---

## Phase prompts

Each session should include exactly one phase prompt from `docs/phases/`:

| File                     | Content                                     |
|--------------------------|---------------------------------------------|
| `phases/01a_INFRA.md`    | Docker, nginx, Makefile, .env               |
| `phases/01b_BACKEND_CORE.md` | config, db, middleware, main, health    |
| `phases/01c_BACKEND_MODELS.md` | ORM models + Alembic migration        |
| `phases/01d_FRONTEND.md` | Vue, Vite, stores, router, views            |
| `phases/01e_TESTS.md`    | pytest conftest + scaffolding tests         |

Send the phase file after this initializer. Do not combine multiple phase
prompts in the same session unless explicitly instructed.
