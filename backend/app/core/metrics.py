"""Prometheus metrics — counters, histograms, and the FastAPI middleware.

Metrics are in-process counters/histograms (no state stored on disk).
Every process instance has its own registry; for multi-worker
deployments a Prometheus-compatible aggregation (PushGateway, a
reverse-proxy sidecar, or a dedicated Prometheus Python multi-process
mode) is the operator's responsibility.

Exposed at ``GET /api/v1/metrics`` in Prometheus text format. The
endpoint is intentionally **unauthenticated** — operators are
expected to firewall the port or front it with an allow-list at the
reverse proxy. See docs/OPERATIONS.md for deployment guidance.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# ── Metric definitions ───────────────────────────────────────────────────────

# Per-request: one counter series + one histogram series per
# (method, path_template, status). Using the route *template* rather
# than the raw URL prevents a cardinality explosion on ID-parametrised
# routes.
REQUEST_COUNT = Counter(
    "aracne2_http_requests_total",
    "Total HTTP requests served.",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "aracne2_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    ),
)

# Authentication — alerts on brute-force ramps and signs of lockout.
LOGIN_ATTEMPTS = Counter(
    "aracne2_login_attempts_total",
    "Login attempts, by outcome.",
    ["outcome"],  # success | failure
)

# Plugin lifecycle — admin-actor-initiated, low volume, but a spike
# is meaningful (configuration drift, activation storm).
PLUGIN_LIFECYCLE = Counter(
    "aracne2_plugin_lifecycle_total",
    "Plugin activate / deactivate / delete events.",
    ["action", "plugin"],  # action: activated | deactivated | deleted
)

# 5xx tracking — cheaper than log-parsing for an alert rule.
UNHANDLED_EXCEPTIONS = Counter(
    "aracne2_unhandled_exceptions_total",
    "Unhandled exceptions that reached the global 500 handler.",
)


# ── Middleware ───────────────────────────────────────────────────────────────


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count + latency for every incoming HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        # Never record the metrics endpoint itself — it would make the
        # counters self-referential and pollute dashboards on every
        # Prometheus scrape.
        path_template = _route_template(request)
        if path_template == "/api/v1/metrics":
            return response

        labels = {
            "method": request.method,
            "path": path_template,
        }
        REQUEST_LATENCY.labels(**labels).observe(duration)
        REQUEST_COUNT.labels(**labels, status=str(response.status_code)).inc()
        return response


def _route_template(request: Request) -> str:
    """Return the matched route template when available, else the raw URL path.

    Using the template (e.g. ``/api/v1/users/{user_id}``) keeps the
    metric cardinality bounded regardless of how many unique IDs are
    hit. When Starlette has not matched a route (404 from the router
    before dispatch), fall back to the raw path; Prometheus will still
    cope but a surge of unknown paths is a useful signal in its own
    right.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


# ── Exposition endpoint helper ───────────────────────────────────────────────


def render_metrics() -> tuple[bytes, str]:
    """Render the current Prometheus exposition text + its content type."""
    return generate_latest(), CONTENT_TYPE_LATEST
