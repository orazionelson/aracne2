"""Webhook Dispatcher — Admin CRUD router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import get_current_user, require_role
from app.models.user import User
from app.plugins._native.webhook_dispatcher.models import WebhookEndpoint
from app.plugins._native.webhook_dispatcher.schemas import (
    SUPPORTED_EVENTS,
    WebhookEndpointCreate,
    WebhookEndpointResponse,
    WebhookEndpointUpdate,
)
from app.plugins._native.webhook_dispatcher.service import dispatch_test, schedule_dispatch
from app.schemas.common import DataResponse

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_admin = Depends(require_role(min_role="Admin"))


def _to_response(m: WebhookEndpoint) -> WebhookEndpointResponse:
    return WebhookEndpointResponse(
        id=m.id,
        label=m.label,
        url=m.url,
        events=m.events,
        secret_set=bool(m.secret),
        active=m.active,
        last_triggered_at=m.last_triggered_at,
        last_status_code=m.last_status_code,
        last_error=m.last_error,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("/events")
async def list_events(_: Annotated[None, _admin]) -> DataResponse[list[str]]:
    """Return the list of supported event names."""
    return DataResponse(data=SUPPORTED_EVENTS)


@router.get("")
async def list_webhooks(
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[WebhookEndpointResponse]]:
    """List all configured webhook endpoints."""
    rows = list(await db.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at)))
    return DataResponse(data=[_to_response(r) for r in rows])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookEndpointCreate,
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[WebhookEndpointResponse]:
    """Create a new webhook endpoint."""
    endpoint = WebhookEndpoint(
        label=body.label,
        url=body.url,
        events=body.events,
        secret=body.secret or None,
        active=body.active,
    )
    db.add(endpoint)
    await db.flush()
    await db.refresh(endpoint)
    return DataResponse(data=_to_response(endpoint))


@router.put("/{endpoint_id}")
async def update_webhook(
    endpoint_id: uuid.UUID,
    body: WebhookEndpointUpdate,
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[WebhookEndpointResponse]:
    """Update a webhook endpoint."""
    endpoint = await db.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if body.label is not None:
        endpoint.label = body.label
    if body.url is not None:
        endpoint.url = body.url
    if body.events is not None:
        endpoint.events = body.events
    if "secret" in body.model_fields_set:
        endpoint.secret = body.secret or None
    if body.active is not None:
        endpoint.active = body.active

    from datetime import UTC, datetime
    endpoint.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(endpoint)
    return DataResponse(data=_to_response(endpoint))


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    endpoint_id: uuid.UUID,
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Delete a webhook endpoint."""
    endpoint = await db.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(endpoint)


@router.post("/{endpoint_id}/test")
async def test_webhook(
    endpoint_id: uuid.UUID,
    _: Annotated[None, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[WebhookEndpointResponse]:
    """Send a test ping to the endpoint and return updated delivery metadata."""
    endpoint = await db.get(WebhookEndpoint, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Webhook not found")
    schedule_dispatch("test.ping", {"message": "Aracne2 webhook test ping"})
    # For the test, fire synchronously so the response reflects the outcome.
    await dispatch_test(db, str(endpoint_id))
    await db.refresh(endpoint)
    return DataResponse(data=_to_response(endpoint))
