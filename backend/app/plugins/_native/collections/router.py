"""
Collections plugin router.

Endpoints are split into three groups declared in this order to avoid
path conflicts:
  1. /collections/public  — unauthenticated public listing
  2. /collections         — authenticated CRUD + workflow
  3. /collections/{id}/…  — per-collection sub-routes
"""

import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.middleware.acl import ROLE_LEVEL, get_current_user, require_role
from app.models.collection import CollectionStatus
from app.models.user import User
from app.schemas.collections import (
    AssignAction,
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
    RejectAction,
    WorkflowAction,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.services.xmldb import (
    assign_collection,
    create_collection,
    delete_collection,
    get_collection,
    list_collections,
    publish_collection,
    reject_collection,
    submit_collection,
    unpublish_collection,
    update_collection,
)

router = APIRouter(prefix="/collections", tags=["collections"])

_auth = Depends(get_current_user)
_eic = Depends(require_role(min_role="EditorInChief"))
_admin = Depends(require_role(min_role="Admin"))


# ── Public endpoint (no auth) ─────────────────────────────────────────────────

@router.get("/public")
async def collections_public(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
) -> PaginatedResponse[CollectionResponse]:
    """List published + is_public collections. No authentication required."""
    from sqlalchemy import func, or_, select
    from app.models.collection import Collection

    stmt = select(Collection).where(
        Collection.status == CollectionStatus.published,
        Collection.is_public.is_(True),
    )
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(Collection.title.ilike(pattern), Collection.slug.ilike(pattern))
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(await db.scalars(
        stmt.order_by(Collection.published_at.desc())
            .offset((page - 1) * per_page).limit(per_page)
    ))
    return PaginatedResponse(
        data=[CollectionResponse.model_validate(r) for r in rows],
        pagination=PaginationMeta(
            page=page, per_page=per_page, total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


# ── Authenticated CRUD ────────────────────────────────────────────────────────

@router.get("")
async def collections_list(
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: CollectionStatus | None = Query(default=None),
    search: str | None = Query(default=None),
) -> PaginatedResponse[CollectionResponse]:
    role: str = request.state.role
    items, total = await list_collections(db, current_user, role, page, per_page, status, search)
    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            page=page, per_page=per_page, total=total,
            total_pages=math.ceil(total / per_page) if total else 0,
        ),
    )


@router.post("", status_code=201)
async def collection_create(
    request: Request,
    body: CollectionCreate,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await create_collection(db, existdb, body, current_user, role)
    return DataResponse(data=data)


@router.get("/{collection_id}")
async def collection_detail(
    collection_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await get_collection(db, collection_id, current_user, role)
    return DataResponse(data=data)


@router.patch("/{collection_id}")
async def collection_update(
    collection_id: uuid.UUID,
    body: CollectionUpdate,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await update_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.delete("/{collection_id}", status_code=204)
async def collection_delete(
    collection_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> None:
    role: str = request.state.role
    await delete_collection(db, existdb, collection_id, current_user, role)


# ── Workflow transitions ───────────────────────────────────────────────────────

@router.post("/{collection_id}/assign")
async def collection_assign(
    collection_id: uuid.UUID,
    body: AssignAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await assign_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/submit")
async def collection_submit(
    collection_id: uuid.UUID,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _auth],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await submit_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/reject")
async def collection_reject(
    collection_id: uuid.UUID,
    body: RejectAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await reject_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/publish")
async def collection_publish(
    collection_id: uuid.UUID,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await publish_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)


@router.post("/{collection_id}/unpublish")
async def collection_unpublish(
    collection_id: uuid.UUID,
    body: WorkflowAction,
    request: Request,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CollectionResponse]:
    role: str = request.state.role
    data = await unpublish_collection(db, collection_id, body, current_user, role)
    return DataResponse(data=data)
