# Email channels

## Overview

Aracne2 sends transactional email through a **local Postfix
container** that the operator deploys alongside the backend. The
backend opens an unauthenticated SMTP connection on the docker
network; Postfix owns the queue, retry, DKIM signing and the relay
to whatever smarthost the operator chooses. The platform therefore
stores **no SMTP secrets** in the database and is vendor-neutral.

Email is opt-in at the platform level (`email_enabled` system
setting, default `false`) and opt-out per user
(`users.email_notifications_enabled`, default `true`).

Three workflow events and one self-service flow are wired through
this channel today:

| Event | Recipient | Template directory |
|---|---|---|
| Collection submitted for review | every active **EditorInChief / Admin** (except the actor) | `email_templates/collection_submitted/` |
| Collection sent back for revisions | the **assigned Editor** | `email_templates/collection_rejected/` |
| Collection published | the **assigned Editor** | `email_templates/collection_published/` |
| Password reset | the requesting user | `email_templates/password_reset/` |

For the user-facing how-to (per-user toggle, what the operator sees
in Settings) see the in-app help page at
**Help → Publishing → Email notifications**, source
[`backend/help_docs/04-publishing/06-email-notifications.md`](../../backend/help_docs/04-publishing/06-email-notifications.md).

For the operator-side rotation / queue-flush runbook see
[OPERATIONS.md](../OPERATIONS.md).

For the original design discussion (why Postfix, why no in-DB SMTP
secrets) see [DEFERRED.md §11](../DEFERRED.md).

---

## Architecture

```
   ┌──────────────┐    SMTP (no auth, no TLS)    ┌──────────────┐
   │  backend     │ ───────────────────────────► │  postfix     │
   │  (FastAPI)   │       port 25 / docker net    │  container   │
   └──────────────┘                                └─────┬────────┘
         ▲                                                │
         │                                                ▼
         │                                        operator's smarthost
         │                                        (DKIM, TLS, SPF, …)
         │
   system_settings
   email_enabled / email_smtp_host / email_smtp_port
   email_from_address / email_from_name / email_subject_prefix
```

The backend → Postfix link is **plaintext on the docker network**
on purpose: no shared secret, no TLS handshake to renew, no
operator-side surprise when the certificate expires. All the
"real" mail-server configuration (relay credentials, DKIM keys,
TLS material to the upstream) lives inside the Postfix container,
managed by the operator with whatever toolchain they prefer.

The Postfix container is declared in
[`docker-compose.yml`](../../docker-compose.yml) under the `email`
profile — it is **not** started by default. To turn email on, the
operator runs:

```bash
docker compose --profile email up -d postfix
# then in Admin → Settings → Email
#   email_enabled = true
#   email_from_address = noreply@example.org
```

---

## Data model

### Existing columns extended

| Table | Column | Migration | Purpose |
|---|---|---|---|
| `users` | `email_notifications_enabled BOOLEAN DEFAULT true` | [`0073`](../../backend/alembic/versions/0073_users_email_notifications_enabled.py) | Per-user opt-out for workflow emails |

### New table `password_reset_tokens`

```
password_reset_tokens
─────────────────────────────
id           UUID PK
user_id      UUID FK → users.id ON DELETE CASCADE
token_hash   VARCHAR(64)   — SHA-256 of the plaintext (plaintext never stored)
expires_at   TIMESTAMPTZ   — created_at + 24h
used_at      TIMESTAMPTZ NULL
created_at   TIMESTAMPTZ
```

**Source**: [`backend/app/models/password_reset_token.py`](../../backend/app/models/password_reset_token.py),
[`backend/alembic/versions/0074_password_reset_tokens.py`](../../backend/alembic/versions/0074_password_reset_tokens.py).

The plaintext token is **never persisted** — only its SHA-256
digest. A DB exfiltration cannot be replayed against accounts; the
digest only allows matching a presented plaintext, not deriving
one.

---

## System settings

All keys live in the `system_settings` table and are surfaced in
the Admin Settings UI. Defaults seeded in
[`backend/app/db/seed.py`](../../backend/app/db/seed.py).

| Key | Default | Purpose |
|---|---|---|
| `email_enabled` | `"false"` | Master switch — `send_mail` is a no-op when false |
| `email_smtp_host` | `"postfix"` | Hostname of the SMTP relay on the docker network |
| `email_smtp_port` | `"25"` | Port number; coerced to `int` at read time |
| `email_from_address` | `""` | `From:` header — required for any send to actually fire |
| `email_from_name` | `"Aracne2"` | Friendly name in the `From:` header |
| `email_subject_prefix` | `"[Aracne2]"` | Prefixed to every outgoing subject |
| `default_language` | `"en"` | Fallback locale when the user's `preferred_lang` has no template |
| `public_base_url` | `""` | Used to build absolute links in email bodies (collection deep links, reset URL) |

`send_mail` returns `False` (and logs a warning) when
`email_enabled = false` or `email_from_address` is empty — the call
never raises. Workflow operations therefore never block on a
misconfigured email channel.

---

## Service layer

### `app.services.email`

| Function | Purpose |
|---|---|
| `send_mail(db, *, to, subject, html, text)` | Async, fire-and-forget-friendly. Returns `bool`, **never raises**. Recipients are SHA-256-hashed in log records — addresses never leak to logs. |
| `render(event, *, lang, default_lang, ctx)` | Loads `email_templates/{event}/{lang}/{subject.txt,body.html,body.txt}` via Jinja2. HTML autoescape on; subject/text autoescape off. Falls back through `requested → default → "en" → first supported`. |
| `is_email_enabled(db)` | Reads the master switch. |

**Source**: [`backend/app/services/email.py`](../../backend/app/services/email.py).

### `app.services.password_reset`

| Function | Purpose |
|---|---|
| `request_reset(db, email_or_username)` | Lookup by email or username (case-insensitive on email); if found mint a 256-bit token, store its SHA-256 with `expires_at = now + 24h`, render the email. **Always returns None** — the public response shape is identical whether the account exists or not. |
| `confirm_reset(db, token, new_password)` | Validate digest → not used → not expired → user active. On success: rehash password, mark token used, **revoke every active session** of the user (mirrors `change_password`), audit. Every failure raises a single `AuthenticationError(INVALID_RESET_TOKEN)` so the client cannot tell which condition failed. |

**Source**: [`backend/app/services/password_reset.py`](../../backend/app/services/password_reset.py).

The token TTL is locked at **24 hours** (constant `TOKEN_TTL`):
long enough to tolerate "I'll handle it tomorrow", short enough
that a leaked link is not a permanent risk.

---

## Hook handlers — `email_dispatcher` plugin

[`backend/app/plugins/_native/email_dispatcher/`](../../backend/app/plugins/_native/email_dispatcher/)

A native plugin that registers three listeners at import time:

```python
hook_registry.register(HookEvent.ON_COLLECTION_SUBMITTED, on_collection_submitted)
hook_registry.register(HookEvent.ON_COLLECTION_REJECTED, on_collection_rejected)
hook_registry.register(HookEvent.ON_COLLECTION_PUBLISHED, on_collection_published)
```

Each handler is **fire-and-forget**: the body runs as
`asyncio.create_task` against its own `AsyncSessionLocal`, catches
every exception, and never propagates back to the workflow
operation that triggered the hook. A failing email therefore
**cannot** block a publish or a submit.

Recipient resolution per event:

| Hook event | Recipient set |
|---|---|
| `collection.submitted` | every active **EiC / Admin** with `email_notifications_enabled = true`, except the actor |
| `collection.rejected` | the **assigned editor** of the collection (if any), if `email_notifications_enabled = true` |
| `collection.published` | same as `rejected` |

The actor is **always excluded** — an EiC who clicks **Publish**
doesn't email themselves.

`HookEvent.ON_COLLECTION_REJECTED` was added in this milestone;
`SUBMITTED` and `PUBLISHED` already existed (used by
`notification_dispatcher`). Source:
[`backend/app/core/hooks.py`](../../backend/app/core/hooks.py).

---

## REST API surface (password reset)

Both endpoints sit under `/api/v1/auth` and are public — anyone on
the network can call them. Rate limited at `STRICT_LIMIT` (10/min
per IP).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/password/reset/request` | Body `{email_or_username: str}`. **Always 204**, even if the account does not exist — caller cannot enumerate. |
| `POST` | `/auth/password/reset/confirm` | Body `{token: str, new_password: str}`. 204 on success; on every failure a single `401 INVALID_RESET_TOKEN` is returned. |

**Source**: [`backend/app/routers/auth.py:282+`](../../backend/app/routers/auth.py#L282).

The frontend pair:

| Path | View |
|---|---|
| `/forgot-password` | [`frontend/src/views/auth/RequestPasswordResetView.vue`](../../frontend/src/views/auth/RequestPasswordResetView.vue) |
| `/reset-password/{token}` | [`frontend/src/views/auth/ConfirmPasswordResetView.vue`](../../frontend/src/views/auth/ConfirmPasswordResetView.vue) |

---

## Templates

Layout under [`backend/app/email_templates/`](../../backend/app/email_templates/):

```
email_templates/
├── collection_submitted/
│   ├── en/{subject.txt, body.html, body.txt}
│   └── it/{subject.txt, body.html, body.txt}
├── collection_rejected/
├── collection_published/
└── password_reset/
```

Each event has a directory per language. Each language has three
files:

- `subject.txt` — subject line (autoescape **off**)
- `body.html` — HTML body (autoescape **on**)
- `body.txt` — plaintext fallback (autoescape **off**)

The Jinja2 environment renders all three. `select_autoescape` keys
on the file extension so the same context dict feeds into every
file safely.

### Render context — workflow events

```python
{
    "actor_name": "Mario Rossi",
    "collection_title": "Epistolario Manzoni",
    "collection_slug": "epistolario-manzoni",
    "collection_url": "https://aracne.example.org/collections/epistolario-manzoni",
    "note": "missing apparatus on letter 12",   # only for ``rejected``
    "recipient_display_name": "Anna Bianchi",
}
```

### Render context — password reset

```python
{
    "recipient_display_name": "Anna Bianchi",
    "reset_url": "https://aracne.example.org/reset-password/<plaintext>",
    "expiry_hours": 24,
}
```

### Language fallback chain

```
requested  →  default_language (system_setting)  →  "en"  →  first supported
```

Each candidate must have a matching `{event}/{lang}/` directory; we
never silently fall back to a missing template — that would render
empty bodies. `render()` raises `FileNotFoundError` when the chain
exhausts; the caller logs and bails out.

---

## Privacy and logging

- Recipient addresses are **never** written to logs in plaintext.
  `_hash_recipient(addr)` produces `"sha256:<16hex>"` so an
  operator can correlate a complaint with a specific outgoing
  message without seeing the address.
- Failed sends log the error string and the SMTP host/port, never
  the body content or the subject.
- Postfix logs (the operator's troubleshooting surface) live in
  the Postfix container and are scoped to the deployment.

---

## Tests

| Path | Coverage |
|---|---|
| [`backend/app/tests/test_email_service.py`](../../backend/app/tests/test_email_service.py) | render fallback, `email_enabled=false` no-op, `from_address` empty no-op, hashed-recipient log redaction |
| [`backend/app/tests/test_email_dispatcher.py`](../../backend/app/tests/test_email_dispatcher.py) | each hook handler resolves the right recipient set, actor excluded, `email_notifications_enabled=false` excluded |
| [`backend/app/tests/test_password_reset.py`](../../backend/app/tests/test_password_reset.py) | mint → confirm → sessions revoked; expired / already-used / wrong-prefix all map to `INVALID_RESET_TOKEN` |
| [`backend/app/tests/test_password_reset_endpoints.py`](../../backend/app/tests/test_password_reset_endpoints.py) | enumeration-resistant 204, single 401 code on every failure |
