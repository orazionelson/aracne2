"""``/admin/gdpr/*`` — Admin-side GDPR request review.

Companion to the user-facing ``POST /users/me/anonymise-request``.
The Admin reviews the open queue, approves (and executes) or
rejects each request. Audit rows are written by the service
layer; this router is just the transport.

Three endpoints, all Admin-gated:

- ``GET    /admin/gdpr/requests`` — list open requests.
- ``POST   /admin/gdpr/anonymise/{request_id}`` — execute the
  anonymise action (replaces identifying metadata with
  placeholders, revokes sessions/PATs, marks the request
  ``completed``).
- ``POST   /admin/gdpr/reject/{request_id}`` — mark the request
  ``rejected``; the user is unaffected.

The endpoints intentionally do NOT expose a "create request on
someone else's behalf" path. An Admin cannot anonymise an
arbitrary user without a corresponding submitted request — the
queue is the audit-shaped surface that connects the user's
intent to the Admin's action.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.middleware.rate_limiter import limiter
from app.models.gdpr_request import GdprRequest
from app.models.user import User
from app.schemas.common import DataResponse
from app.services.gdpr import (
    anonymise_user_metadata,
    list_open_requests,
    reject_anonymise_request,
)


router = APIRouter(prefix="/admin/gdpr", tags=["gdpr"])
_admin = Depends(require_role(min_role="Admin"))


class GdprRequestView(BaseModel):
    """One entry in the Admin's open-requests queue."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_username: str | None = None
    kind: str
    status: str
    reason: str | None = None
    submitted_at: str
    reviewed_at: str | None = None
    review_notes: str | None = None


class ReviewBody(BaseModel):
    """Body for approve / reject endpoints — just the review notes.

    The notes are mandatory in spirit (the Admin records the
    rationale that lets a future audit reconstruct the decision),
    but the schema marks them optional so an empty string isn't a
    422. The service layer trims empty values to ``None``.
    """

    review_notes: str | None = None


async def _to_view(db: AsyncSession, row: GdprRequest) -> GdprRequestView:
    user = await db.get(User, row.user_id)
    return GdprRequestView(
        id=row.id,
        user_id=row.user_id,
        user_username=user.username if user else None,
        kind=row.kind,
        status=row.status,
        reason=row.reason,
        submitted_at=row.submitted_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        review_notes=row.review_notes,
    )


@router.get("/requests")
@limiter.limit("60/minute")
async def list_requests(
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[list[GdprRequestView]]:
    """Return every request not yet completed or rejected, newest first."""
    rows = await list_open_requests(db)
    return DataResponse(
        data=[await _to_view(db, r) for r in rows]
    )


@router.post("/anonymise/{request_id}")
@limiter.limit("10/minute")
async def execute_anonymise(
    request: Request,
    request_id: uuid.UUID,
    body: ReviewBody,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GdprRequestView]:
    """Run the anonymise action against the user the request covers.

    Replaces identifying fields on the user row with stable
    placeholders, rewrites every audit_log row's actor_username
    referencing the user with the same placeholder, revokes
    sessions + PATs, marks the request ``completed``. The
    editorial record (authorship of published documents, version
    rows authored by the user) is preserved.
    """
    row = await db.get(GdprRequest, request_id)
    if row is None:
        raise NotFoundError(f"GDPR request {request_id} not found.")
    await anonymise_user_metadata(
        db, request=row, actor=current_user, review_notes=body.review_notes
    )
    return DataResponse(data=await _to_view(db, row))


@router.post("/reject/{request_id}")
@limiter.limit("10/minute")
async def reject_request(
    request: Request,
    request_id: uuid.UUID,
    body: ReviewBody,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GdprRequestView]:
    """Mark the request rejected without touching the user's data.

    ``review_notes`` should carry the reasoning so a future audit
    can reconstruct the decision (e.g. "no court order; pending
    external legal review").
    """
    row = await db.get(GdprRequest, request_id)
    if row is None:
        raise NotFoundError(f"GDPR request {request_id} not found.")
    await reject_anonymise_request(
        db, request=row, actor=current_user, review_notes=body.review_notes
    )
    return DataResponse(data=await _to_view(db, row))
