# Capability roles

## Overview

A **capability role** is orthogonal to the five-step hierarchical
role ladder (`User` < `Editor` ≈ `Designer` < `EditorInChief` <
`Admin`). It is granted explicitly per user, never inferred from
the hierarchy, and unlocks one specific surface of the platform
without changing the user's main role.

The first concrete capability is **`PolicyManager`**, shipped in
Milestone 3 (FUTURE_IDEAS §27). Future capabilities like
`Translator` or `Annotator` would land as additional values of
the `RoleName` enum without API changes.

For the user-facing how-to (where the toggle lives, how to
reassign) see the in-app help at
**Help → Reference → Policy pages**, source
[`backend/help_docs/05-reference/06-policy-pages.md`](../../backend/help_docs/05-reference/06-policy-pages.md).

---

## How it differs from hierarchical roles

| | Hierarchical | Capability |
|---|---|---|
| Stored in | `roles` table | `roles` table |
| `kind` column value | `"hierarchical"` | `"capability"` |
| Numeric level | yes (`ROLE_LEVEL` map) | no |
| Granted by | Admin via user-edit form | Admin via dedicated capability surface |
| Held by | many users | many users (or singleton) |
| Checked by | `require_role(min_role=…)` | `require_capability(name)` |
| Admin always passes | yes (level 4 ≥ everything) | yes (Admin override in `user_has_capability`) |

---

## Schema

[`backend/alembic/versions/0081_capability_roles.py`](../../backend/alembic/versions/0081_capability_roles.py)
extends `roles` with two columns:

```
roles
─────────────────────────────
…existing columns…
kind        VARCHAR(16)  DEFAULT 'hierarchical'
singleton   BOOLEAN      DEFAULT false
```

Existing five rows are migrated as `kind='hierarchical', singleton=false`.
The `role_name` PostgreSQL enum is extended with `PolicyManager`
via `ALTER TYPE … ADD VALUE` (autocommit block — required by
PostgreSQL for enum value addition). A new row is inserted as
`kind='capability', singleton=true`.

The Python `RoleName` enum gains the new value; the `RoleKind`
enum is added (`hierarchical` | `capability`).

**Source**:
[`backend/app/models/role.py`](../../backend/app/models/role.py).

---

## Singleton constraint

A capability role with `singleton=true` may have **at most one
active holder** at any moment. Granting it to user B while user A
already holds it auto-revokes A in the same transaction; the
audit log captures the operation as one `role.transferred` row,
not two unrelated `role.assigned` / `role.revoked` events.

**Why singleton for `PolicyManager`**: a single named
accountability holder for institutional policy content matches
the way real organisations assign that responsibility. Two
simultaneous holders disagreeing on a policy edit would be a
governance ambiguity the platform shouldn't introduce.

Future capabilities can declare themselves multi-holder simply by
inserting their row with `singleton=false`. The pattern is
generic.

---

## Service surface

`backend/app/services/roles.py`:

| Function | Purpose |
|---|---|
| `get_capability_holder(db, *, role_name)` | Return the active holder (User), or None |
| `user_has_capability(db, *, user, capability)` | True when *user* holds the capability OR is Admin |
| `transfer_singleton_role(db, *, role_name, target_user, actor)` | Transactionally revoke previous + grant target; one `role.transferred` audit row; idempotent on "target already holds it" |
| `revoke_singleton_role(db, *, role_name, actor)` | Revoke from current holder; idempotent on already-unassigned |

`user_has_capability` always returns `True` for Admin users —
locking Admin out of a capability they manage would be more
confusing than useful. Every other role goes through an explicit
membership check on `user_roles` filtered by the capability's
role row.

---

## Middleware

`backend/app/middleware/acl.py:require_capability(name)` is the
FastAPI dependency that gates a route on a capability:

```python
from app.middleware.acl import require_capability

@router.post("/policies/{slug}/save")
async def save_policy(
    current_user: Annotated[User, Depends(require_capability("PolicyManager"))],
    …
): ...
```

It depends transitively on `_get_current_user` so the user is
already populated; the membership check happens inside the
dependency. Admin users always pass.

`require_capability` and `require_role` are independent — the
same route can require both (e.g. a hypothetical "Editor + holds
the `BibliographyReviewer` capability" guard).

---

## REST API surface

All under `/api/v1/admin/capabilities/{role_name}`, all Admin-gated.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/capabilities/{role_name}` | Return current holder (or null) |
| `PUT` | `/admin/capabilities/{role_name}` | Body `{user_id}` — transfer to target |
| `DELETE` | `/admin/capabilities/{role_name}` | Revoke from current holder |

`role_name` is the `RoleName` enum value as a string
(e.g. `"PolicyManager"`). The endpoints work for any singleton
capability defined in the schema — adding a new capability
doesn't require new routes.

**Source**:
[`backend/app/routers/capabilities.py`](../../backend/app/routers/capabilities.py).

---

## Audit log

`role.transferred` audit rows carry both legs of the swap:

```jsonc
{
  "action": "role.transferred",
  "actor_username": "alice_admin",
  "target_type": "role",
  "target_id": "PolicyManager",
  "target_label": "PolicyManager",
  "payload": {
    "from_user_id": "8c2b…",
    "from_username": "old_holder",
    "to_user_id": "ab21…",
    "to_username": "new_holder"
  }
}
```

A first-time grant (no previous holder) writes `from_user_id: null`.
A revoke writes `role.revoked` instead. Both surface in the
`/admin/audit-log` view.

---

## Frontend

The PolicyManager card lives at the top of `/admin/policies`
([`frontend/src/views/admin/PolicyPagesView.vue`](../../frontend/src/views/admin/PolicyPagesView.vue))
showing "Current PolicyManager: [user X]" plus the Change
button — under the hood it calls
`PUT /admin/capabilities/PolicyManager` with the new user's id.

Future capabilities could surface a similar card on a different
admin view (e.g. `/admin/users` for capabilities that don't have
a single dedicated UI page).

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/tests/test_capability_roles.py`](../../backend/app/tests/test_capability_roles.py) | 11 tests — service-level transitions (unassigned → assigned → transferred → revoked → re-revoked-idempotent), Admin override on `user_has_capability`, REST round-trip |

---

## Adding a new capability

Checklist:

1. Add the value to `RoleName` in
   [`backend/app/models/role.py`](../../backend/app/models/role.py).
2. Write an Alembic migration that:
   - extends the `role_name` PostgreSQL enum (autocommit block);
   - inserts the row with `kind='capability'` + the chosen
     `singleton` value.
3. Update [`backend/app/db/seed.py`](../../backend/app/db/seed.py)'s
   `ROLES` list so a fresh deployment seeds the new row.
4. Use `Depends(require_capability("YourCapability"))` on the
   endpoints that should be gated.
5. (For singletons) the existing `/admin/capabilities/{name}`
   surface already works for the new role — no router changes
   needed.
6. Frontend: render a "Current X" card wherever the capability
   is most discoverable.

For a multi-holder capability, the existing transfer flow doesn't
fit — you'd ship a `POST /admin/capabilities/{name}/grant` and a
matching `DELETE /admin/capabilities/{name}/{user_id}`. The
service-layer primitives can grow `grant_role` / `revoke_role`
(non-singleton variants) without touching the singleton path.
