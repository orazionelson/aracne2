# Notifications

## Overview

Aracne2 has a built-in in-app notification system. Notifications are created
server-side by the `notification_dispatcher` plugin in response to platform events
(collection state changes, document uploads, user actions) and delivered to the
target user's inbox. Users read and dismiss notifications through the bell icon
in the navbar.

Notifications are **per-user**, **persisted** in PostgreSQL, and **never pushed** in
real time — the frontend polls the unread count on a configurable interval.

---

## Data model

```
notifications
─────────────────────────────
id            BIGINT  PK
user_id       UUID    FK → users.id ON DELETE CASCADE
type          VARCHAR(128)   — e.g. "collection.published"
title         VARCHAR(512)
body          TEXT | NULL
link          TEXT | NULL    — internal path (e.g. "/collections/my-slug")
is_read       BOOLEAN        — default FALSE
created_at    TIMESTAMPTZ
read_at       TIMESTAMPTZ | NULL
```

**File**: `backend/app/models/notification.py`

**`type`** is a free-form string set by the dispatcher. Current values:

| Type | Trigger |
|---|---|
| `collection.submitted` | Collection moved to "submitted" status |
| `collection.published` | Collection published |
| `collection.unpublished` | Collection reverted to draft |
| `document.uploaded` | Batch document upload completed |
| `user.created` | New user registered |

---

## Backend

### Files

| Path | Role |
|---|---|
| `backend/app/models/notification.py` | SQLAlchemy ORM model |
| `backend/app/schemas/notifications.py` | Pydantic response schema |
| `backend/app/routers/notifications.py` | FastAPI router |
| `backend/app/services/notifications.py` | Business logic (list, mark read, delete) |
| `backend/app/plugins/_native/notification_dispatcher/plugin.py` | Hook listener — creates notification rows |

### Endpoints

All endpoints require `[auth]` — any authenticated user. Users can only access
their own notifications.

---

#### `GET /api/v1/notifications/unread-count`

Returns the number of unread notifications for the current user.

**Response `200`**:
```jsonc
{ "data": 3 }
```

The frontend polls this endpoint to update the navbar badge.

---

#### `GET /api/v1/notifications`

Paginated notification list.

**Query parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number (≥ 1) |
| `per_page` | int | 20 | Items per page (1–100) |
| `unread_only` | bool | false | If `true`, return only unread notifications |

**Response `200`**:
```jsonc
{
  "data": [
    {
      "id": 42,
      "type": "collection.published",
      "title": "Collection published",
      "body": "\"Epistolario Manzoni\" has been published.",
      "link": "/collections/epistolario-manzoni",
      "is_read": false,
      "created_at": "2026-04-16T10:30:00Z",
      "read_at": null
    }
  ],
  "pagination": { "page": 1, "per_page": 20, "total": 1, "total_pages": 1 }
}
```

---

#### `PATCH /api/v1/notifications/{notification_id}/read`

Mark a single notification as read. Sets `is_read = true` and `read_at = now()`.

**Response `200`**: updated notification object (same shape as list item).

---

#### `POST /api/v1/notifications/read-all`

Mark **all** unread notifications for the current user as read in one call.

**Response `200`**:
```jsonc
{ "data": 5 }   // number of notifications updated
```

---

#### `DELETE /api/v1/notifications/{notification_id}`

Permanently delete a single notification. Only the owner can delete their own notifications.

**Response `204`**: no body.

---

### Creating notifications (plugin API)

The `notification_dispatcher` plugin listens to hook events and calls:

```python
# backend/app/plugins/_native/notification_dispatcher/plugin.py
from app.services.notifications import create_notification

await create_notification(
    db,
    user_id=target_user.id,
    type="collection.published",
    title="Collection published",
    body=f'"{col.title}" has been published.',
    link=f"/collections/{col.slug}",
)
```

The dispatcher determines the target user(s) from the hook event payload.
For collection events the target is typically the assigned Editor.

---

## Frontend

### Files

| Path | Role |
|---|---|
| `frontend/src/stores/notifications.ts` | Pinia store — notification state and API calls |
| `frontend/src/views/NotificationsView.vue` | Full notification inbox page |
| `frontend/src/components/layout/NotificationBell.vue` | Navbar badge + dropdown preview |

### Store (`useNotificationsStore`)

```typescript
// Key state
const notifications = ref<Notification[]>([])
const unreadCount = ref(0)
const loading = ref(false)

// Key actions
async function fetchUnreadCount()          // GET /notifications/unread-count
async function fetchNotifications(page, perPage, unreadOnly)
async function markRead(id: number)        // PATCH /{id}/read
async function markAllRead()              // POST /read-all
async function remove(id: number)         // DELETE /{id}
```

### Polling

The navbar component calls `fetchUnreadCount()` on mount and then every **30 seconds**
via `setInterval`. The interval is cleared when the component unmounts.

### Notification inbox

`NotificationsView` renders a paginated list with:
- Unread badge on each item
- "Mark all as read" button
- Per-item actions: mark read / delete
- Optional `unread_only` toggle
- Click on a notification with a `link` navigates to the target view

---

## Security

| Concern | Mitigation |
|---|---|
| Ownership | Service layer filters by `user_id = current_user.id` — cross-user access is impossible |
| Deletion | `delete_notification()` verifies ownership before deleting |
| Data minimization | `link` is an internal path, never a user-controlled URL; stored as plain text, not rendered as HTML |
