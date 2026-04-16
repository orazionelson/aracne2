# Health Check

## Overview

Aracne2 exposes a `GET /api/v1/health` endpoint that checks live connectivity to
both backend dependencies — PostgreSQL and eXist-db — and returns an overall status.
The endpoint is **public** (no authentication required) and is designed for use by:

- Docker / Kubernetes liveness and readiness probes
- External uptime monitors (UptimeRobot, Pingdom, etc.)
- The Aracne2 admin dashboard (shows service status at a glance)

---

## Endpoint

### `GET /api/v1/health` [pub]

**File**: `backend/app/routers/health.py`

Performs two live checks on every call:

1. **PostgreSQL** — executes `SELECT 1` via the async SQLAlchemy session
2. **eXist-db** — calls `ExistDBClient.ping()` (a lightweight HTTP GET to the eXist REST API)

Returns overall `"healthy"` only when both services respond without error.
Any failure flips the status to `"degraded"`.

**Response `200`** (both services up):
```jsonc
{
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "environment": "development",
    "services": {
      "postgres": { "status": "ok", "detail": null },
      "existdb":  { "status": "ok", "detail": null }
    }
  }
}
```

**Response `200`** (eXist-db down — in development mode):
```jsonc
{
  "data": {
    "status": "degraded",
    "version": "1.0.0",
    "environment": "development",
    "services": {
      "postgres": { "status": "ok",    "detail": null },
      "existdb":  { "status": "error", "detail": null }
    }
  }
}
```

> **Note**: the endpoint always returns HTTP `200` — the overall status is in the
> `data.status` field. Monitors should check `data.status == "healthy"`.

### Detail field

In **development** mode (`ENVIRONMENT=development`), `detail` may contain the raw
exception message from a failed PostgreSQL connection. In **production** it is always
`null` to avoid leaking internal error details.

---

## Schemas

```python
# backend/app/schemas/common.py

class HealthService(BaseModel):
    status: str          # "ok" | "error"
    detail: str | None   # error message — development only

class HealthResponse(BaseModel):
    status: str          # "healthy" | "degraded"
    version: str
    environment: str
    services: dict[str, HealthService]
```

---

## Docker healthcheck

The `docker-compose.yml` uses this endpoint for the backend container's healthcheck:

```yaml
healthcheck:
  test: ["CMD", "curl", "-sf", "http://localhost:8000/api/v1/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
```

Other services (`postgres`, `existdb`) have their own native healthchecks configured
in `docker-compose.yml`. The backend healthcheck depends on both being healthy before
the backend container is considered ready.

---

## Deployment monitoring

For external monitors, configure an HTTP check on:

```
GET https://aracne.example.org/api/v1/health
```

Assert:
- HTTP status code `200`
- Response body JSON path `$.data.status` equals `"healthy"`

Some monitors (e.g. UptimeRobot) support keyword checks — assert the body contains
`"healthy"` and does **not** contain `"degraded"`.

---

## Frontend

The admin dashboard (`frontend/src/views/HomeView.vue` + `frontend/src/stores/dashboard.ts`)
calls `GET /health` on load and displays a service status panel showing:

- Overall platform status (green / red badge)
- Per-service status: PostgreSQL, eXist-db
- Last checked timestamp

The panel auto-refreshes every 60 seconds while the dashboard is open.
