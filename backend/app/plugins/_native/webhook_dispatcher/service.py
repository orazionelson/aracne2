"""Webhook Dispatcher — delivery service.

Outgoing request format:
  POST <url>
  Content-Type: application/json
  X-Aracne-Event: <event>
  X-Aracne-Signature: sha256=<hmac-hex>   (only when secret is set)

  {
    "event": "collection.published",
    "timestamp": "2026-04-09T10:00:00+00:00",
    "payload": { ... }
  }

Delivery is attempted up to MAX_RETRIES times with exponential backoff.
Results (status code, error) are persisted on the WebhookEndpoint row.
"""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.plugins._native.webhook_dispatcher.models import WebhookEndpoint
from app.plugins._native.webhook_dispatcher.schemas import SUPPORTED_EVENTS

logger = structlog.get_logger()

_TIMEOUT = 10.0    # seconds per attempt
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds: 2, 4


def _build_headers(endpoint: WebhookEndpoint, body: str, event: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Aracne2-Webhook/1.0",
        "X-Aracne-Event": event,
    }
    if endpoint.secret:
        sig = hmac.new(
            endpoint.secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Aracne-Signature"] = f"sha256={sig}"
    return headers


async def _deliver_once(url: str, body: str, headers: dict[str, str]) -> int:
    """Send one HTTP POST. Returns the response status code."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, content=body, headers=headers)
        resp.raise_for_status()
        return resp.status_code


async def _deliver(db: AsyncSession, endpoint: WebhookEndpoint, event: str, payload: dict[str, Any]) -> None:
    """Deliver one event to one endpoint with retries. Updates endpoint delivery metadata."""
    body = json.dumps(
        {"event": event, "timestamp": datetime.now(UTC).isoformat(), "payload": payload},
        ensure_ascii=False,
    )
    headers = _build_headers(endpoint, body, event)
    status_code: int | None = None
    error_msg: str | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            status_code = await _deliver_once(endpoint.url, body, headers)
            error_msg = None
            break
        except httpx.TimeoutException:
            error_msg = "Request timed out"
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_msg = f"HTTP {status_code}"
            break  # 4xx/5xx — no retry (deterministic failure)
        except httpx.RequestError as exc:
            error_msg = f"Connection error: {exc}"

        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_BACKOFF_BASE ** attempt)

    endpoint.last_triggered_at = datetime.now(UTC)
    endpoint.last_status_code = status_code
    endpoint.last_error = error_msg
    endpoint.updated_at = datetime.now(UTC)
    await db.commit()

    log = logger.bind(webhook_id=str(endpoint.id), event=event, url=endpoint.url)
    if error_msg:
        log.warning("webhook_delivery_failed", error=error_msg, status_code=status_code)
    else:
        log.info("webhook_delivered", status_code=status_code)


async def dispatch_event(db: AsyncSession, event: str, payload: dict[str, Any]) -> None:
    """Send *event* to all active endpoints subscribed to it."""
    if event not in SUPPORTED_EVENTS:
        return
    rows = list(
        await db.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.active.is_(True),
                WebhookEndpoint.events.contains([event]),
            )
        )
    )
    for endpoint in rows:
        await _deliver(db, endpoint, event, payload)


async def dispatch_test(db: AsyncSession, endpoint_id: str) -> tuple[int | None, str | None]:
    """Send a synthetic test ping to one endpoint. Returns (status_code, error)."""
    from app.db.postgres import AsyncSessionLocal

    endpoint = await db.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        return None, "Endpoint not found"

    async with AsyncSessionLocal() as bg_db:
        await _deliver(
            bg_db,
            await bg_db.get(WebhookEndpoint, endpoint_id),  # type: ignore[arg-type]
            "test.ping",
            {"message": "Aracne2 webhook test ping"},
        )
    # Re-read updated delivery metadata
    await db.refresh(endpoint)
    return endpoint.last_status_code, endpoint.last_error


def schedule_dispatch(event: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget: schedule delivery in a background asyncio task.

    Opens its own AsyncSession so the caller's transaction can commit
    independently.  Call this from hook handlers.
    """
    from app.db.postgres import AsyncSessionLocal

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await dispatch_event(db, event, payload)

    asyncio.create_task(_run())
