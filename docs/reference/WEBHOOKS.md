# Webhook Dispatcher

## Overview

The Webhook Dispatcher plugin lets an Admin configure external HTTP endpoints to
receive real-time event notifications when significant things happen in Aracne2
(collection published, document uploaded, user created, etc.).

Each webhook endpoint is a URL + event subscription list + optional HMAC secret.
When a subscribed event fires, the dispatcher sends a `POST` request to the URL
with a JSON payload. Delivery outcome (HTTP status code, error) is stored on the
endpoint record for visibility.

---

## Data model

```
webhook_endpoints
─────────────────────────────
id                  UUID    PK
label               VARCHAR(256)        — human-readable name
url                 TEXT               — target HTTP/HTTPS URL
events              JSON               — list[str] of subscribed event names
secret              TEXT | NULL        — HMAC-SHA256 signing key (stored in clear)
active              BOOLEAN            — if false, no dispatches are sent
last_triggered_at   TIMESTAMPTZ | NULL
last_status_code    INTEGER | NULL     — HTTP response code of last delivery
last_error          TEXT | NULL        — error message of last failed delivery
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

**File**: `backend/app/plugins/_native/webhook_dispatcher/models.py`

The `secret` field stores the raw secret. It is **never returned** in API responses
(the `secret_set: bool` field indicates only whether a secret is configured).

---

## Supported events

| Event name | Trigger |
|---|---|
| `collection.submitted` | Collection workflow state → submitted |
| `collection.published` | Collection published |
| `collection.unpublished` | Collection reverted to draft |
| `document.uploaded` | Document(s) uploaded to a collection |
| `document.deleted` | Document deleted from a collection |
| `user.created` | New user account created |

The full list is available at `GET /api/v1/webhooks/events` and is defined in
`backend/app/plugins/_native/webhook_dispatcher/schemas.py` (`SUPPORTED_EVENTS`).

---

## Payload format

Every delivery `POST` carries a JSON body:

```jsonc
{
  "event": "collection.published",
  "timestamp": "2026-04-16T12:00:00Z",
  "data": {
    // event-specific fields — e.g. collection slug, title, user id
  }
}
```

### HMAC signature

When a `secret` is set, the dispatcher adds an `X-Aracne2-Signature` header:

```
X-Aracne2-Signature: sha256=<hex_digest>
```

The signature is `HMAC-SHA256(secret, raw_body_bytes)`. The receiving service
should verify the header to reject forged payloads.

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/plugins/_native/webhook_dispatcher/models.py` | ORM model (`WebhookEndpoint`) |
| `backend/app/plugins/_native/webhook_dispatcher/schemas.py` | Pydantic schemas + `SUPPORTED_EVENTS` |
| `backend/app/plugins/_native/webhook_dispatcher/router.py` | FastAPI router |
| `backend/app/plugins/_native/webhook_dispatcher/service.py` | `schedule_dispatch()`, `dispatch_test()` |
| `backend/app/plugins/_native/webhook_dispatcher/plugin.py` | Hook listeners |

### Endpoints

All endpoints require `[A]` (Admin only).

---

#### `GET /api/v1/webhooks/events`

Return the list of supported event names.

**Response `200`**:
```jsonc
{ "data": ["collection.submitted", "collection.published", ...] }
```

---

#### `GET /api/v1/webhooks`

List all configured webhook endpoints.

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": "3fa85f64-...",
      "label": "Slack notifications",
      "url": "https://hooks.slack.com/...",
      "events": ["collection.published"],
      "secret_set": true,
      "active": true,
      "last_triggered_at": "2026-04-15T09:00:00Z",
      "last_status_code": 200,
      "last_error": null,
      "created_at": "2026-03-01T00:00:00Z",
      "updated_at": "2026-04-15T09:00:00Z"
    }
  ]
}
```

---

#### `POST /api/v1/webhooks`

Create a new webhook endpoint.

**Request body**:
```jsonc
{
  "label": "Slack notifications",
  "url": "https://hooks.slack.com/services/...",
  "events": ["collection.published", "collection.unpublished"],
  "secret": "mysecret",   // optional
  "active": true
}
```

**Validation**:
- `url` is SSRF-guarded: private IP ranges and loopback addresses are rejected
- `events` must be a non-empty subset of `SUPPORTED_EVENTS`
- Duplicate events are deduplicated (order preserved)

**Response `201`**: created endpoint object.

---

#### `PUT /api/v1/webhooks/{endpoint_id}`

Full update of an existing endpoint. All fields are optional (PATCH semantics).

**Request body**: same fields as POST, all optional.

**Sending `"secret": null`** removes the existing secret.
**Omitting `"secret"`** leaves the existing secret unchanged.

**Response `200`**: updated endpoint object.

---

#### `DELETE /api/v1/webhooks/{endpoint_id}`

Delete an endpoint. No more dispatches will be sent.

**Response `204`**: no body.

---

#### `POST /api/v1/webhooks/{endpoint_id}/test`

Send a test `test.ping` event to the endpoint synchronously and return the updated
delivery metadata (`last_triggered_at`, `last_status_code`, `last_error`).

**Response `200`**: updated endpoint object reflecting the test delivery outcome.

---

### Dispatch mechanism

```python
# backend/app/plugins/_native/webhook_dispatcher/service.py

def schedule_dispatch(event: str, data: dict) -> None:
    """Queue a dispatch for all active endpoints subscribed to event."""
    ...

async def dispatch_test(db: AsyncSession, endpoint_id: str) -> None:
    """Fire a test.ping synchronously and update delivery metadata."""
    ...
```

`schedule_dispatch` is called from hook listeners in `plugin.py`. In v1 it is
**synchronous** — dispatches happen in-process during the request that triggered
the hook. A future version will offload to an async task queue (see `DEFERRED.md`).

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/views/admin/WebhooksView.vue` | Admin management page |

### Admin UI

The webhooks management page (Admin → Webhooks) provides:
- List of all endpoints with status (active/inactive, last delivery result)
- Create / edit / delete endpoint form
- Event subscription checkboxes (loaded from `GET /webhooks/events`)
- "Send test ping" button — triggers `POST /{id}/test` and shows the response
- Visual indicator for last delivery outcome (green 2xx, red 4xx/5xx, grey = never triggered)

---

## Security

| Concern | Mitigation |
|---|---|
| SSRF | `url` is validated by `check_ssrf()` — private IPs, loopback, link-local are rejected |
| Secret exposure | `secret` is never returned in API responses; `secret_set: bool` is used instead |
| Event filtering | Only `SUPPORTED_EVENTS` are accepted — arbitrary event names are rejected |
| Access control | All endpoints require Admin role |
| Delivery timeouts | HTTP client uses a fixed timeout to prevent slow-loris hangs on the target server |
