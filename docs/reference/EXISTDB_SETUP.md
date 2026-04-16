# eXist-db Setup and Security Model

## Overview

Aracne2 uses eXist-db 6.x as its native XML database (Layer 2). All TEI documents
are stored and queried here. This document covers the user model, collection
namespace, bootstrap process, and environment variables.

---

## Collection namespace

All Aracne2 data lives under a single root path inside eXist-db:

```
/db/aracne2/
└── collections/
    ├── dante/
    │   ├── doc1.xml
    │   └── doc2.xml
    └── manzoni/
        └── lettera-001.xml
```

| Path | Purpose |
|---|---|
| `/db/aracne2/` | Aracne2 root — created at startup if absent |
| `/db/aracne2/collections/` | Parent of all editorial collections |
| `/db/aracne2/collections/{slug}/` | One directory per collection (slug = URL-safe identifier) |

This namespace isolates all Aracne2 data from any other applications that may be
installed in the same eXist-db instance (e.g. eXide, eXist-db Package Manager apps).

---

## User model — least-privilege design

Aracne2 maintains **two eXist-db users** and keeps their roles strictly separate:

| User | Role | Used for |
|---|---|---|
| `admin` | eXist-db built-in superuser | Bootstrap only: creating the root collection, creating the `aracne` account, setting ownership |
| `aracne` | Dedicated runtime account (group: `guest`) | All runtime operations: XQuery execution, document CRUD, collection management |

The `admin` user is used **only at startup** (`ensure_root` and `bootstrap_user` XQuery
calls), then is not used again until the next restart. All HTTP queries issued during
normal operation authenticate as `aracne`.

This follows the **principle of least privilege**: a compromised backend process can
only access the `/db/aracne2/` subtree, not the eXist-db system collections or any
other installed application.

### Permissions on `/db/aracne2/`

After bootstrap, the entire `/db/aracne2/` tree is owned by `aracne`:

| Resource type | Permissions |
|---|---|
| Collections | `rwx------` (owner full, group none, others none) |
| Documents | `rw-------` (owner read/write, group none, others none) |

New collections and documents created by the backend inherit these permissions
automatically because `aracne` is the creating user.

---

## Bootstrap process

At every startup, the backend lifespan executes two idempotent XQuery files under
admin credentials:

### 1. `ensure_root.xq`

Creates `/db/aracne2` and `/db/aracne2/collections` if they do not exist.
Safe to call on every startup — uses `xmldb:collection-available()` guards.

### 2. `bootstrap_user.xq`

1. Creates the `aracne` account if it does not exist (`sm:user-exists` guard).
2. Recursively walks the entire `/db/aracne2/` tree and transfers ownership
   of every collection and document to `aracne` (`sm:chown`, `sm:chgrp`, `sm:chmod`).

This is safe to call on every startup:
- Accounts are never duplicated.
- `chown`/`chmod` on already-owned resources are no-ops from a data perspective.
- Pre-existing collections created under `admin` (before least-privilege was introduced)
  are migrated to `aracne` ownership on the first restart after bootstrap is enabled.

**Bootstrap is skipped** (with a `warning` log event `existdb_bootstrap_skipped`)
if `EXISTDB_APP_PASSWORD` is not set. The backend starts normally but the runtime
client falls back to admin credentials — not recommended for production.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `EXISTDB_URL` | Yes | Base URL of the eXist-db REST API, e.g. `http://existdb:8080` |
| `EXISTDB_USER` | Yes | Runtime account name — set to `aracne` |
| `EXIST_PASSWORD` | Yes (production) | eXist-db admin password. Set manually via the eXist-db Dashboard or REST API, then copy here. eXist-db starts with an **empty** admin password on first boot. |
| `EXISTDB_APP_PASSWORD` | Yes (production) | Password for the `aracne` runtime user. Created at bootstrap. Must be set before the first startup. |

### First-run sequence

1. Start the stack with `make up` — eXist-db starts with an empty admin password.
2. Set `EXIST_PASSWORD=` (leave empty) and `EXISTDB_APP_PASSWORD=<choose_a_password>` in `.env`.
3. Run `docker compose up -d backend` (recreates the container to pick up new env vars).
4. The backend creates the `aracne` user automatically on startup.
5. Optionally verify in the eXist-db Dashboard → User Manager that `aracne` exists.

> **Note:** Use `docker compose up -d backend` (not `restart`) when changing `.env`
> variables. `restart` does not re-read `env_file`; `up -d` recreates the container
> with the updated environment.

### Changing the admin password (production)

```bash
# 1. Set the new password in the eXist-db Dashboard (Security → Users → admin → Edit)
# 2. Update .env
EXIST_PASSWORD=new_admin_password
# 3. Recreate the backend container
docker compose up -d backend
```

---

## Two HTTP clients in ExistDBClient

The `ExistDBClient` class (`backend/app/db/existdb.py`) maintains two
`httpx.AsyncClient` instances with different credentials:

| Attribute | Credentials | Used by |
|---|---|---|
| `_admin_client` | `admin` / `EXIST_PASSWORD` | `ensure_root()`, `bootstrap_user()` |
| `_client` | `aracne` / `EXISTDB_APP_PASSWORD` | All public methods: `xquery()`, `get_document()`, `put_document()`, `delete_document()`, `create_collection()`, `delete_collection()`, `list_collection()` |

Both clients are opened in `connect()` (called during lifespan startup) and closed
in `close()` (called during lifespan shutdown).

---

## Checking the setup

After startup, verify in the eXist-db Dashboard (`http://localhost:8080/exist/apps/dashboard`):

1. **User Manager → Users**: `aracne` appears in the list.
2. **DB Manager → `/db/aracne2/`**: Owner is `aracne`, permissions `rwx------`.
3. **DB Manager → `/db/aracne2/collections/`**: Same.
4. Any collection subdirectory (e.g. `/db/aracne2/collections/prova`): Owner `aracne`.

---

## XQuery files

All eXist-db interaction from the backend goes through `.xq` files in
`backend/app/xqueries/`. Relevant system-level files:

| File | Credentials | Purpose |
|---|---|---|
| `system/ensure_root.xq` | admin | Creates `/db/aracne2` and `/db/aracne2/collections` |
| `system/bootstrap_user.xq` | admin | Creates `aracne` account; recursively sets ownership |

Runtime XQuery files (collections, documents, search, …) in the other subdirectories
all execute under the `aracne` credentials via `_client`.
