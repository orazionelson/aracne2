"""Named Entity Index — REST router.

Route order matters: /admin/* static paths are declared BEFORE /{entity_id}
parameterised paths to avoid routing ambiguity.

Public endpoints (no auth):
  GET  /entities                        — paginated entity list
  GET  /entities/{id}/occurrences       — occurrences for one entity

Admin endpoints (Admin role):
  GET  /entities/admin                  — admin entity list (all collections)
  PUT  /entities/admin/{id}             — update canonical_form / authority_ref
  DELETE /entities/admin/{id}           — delete entity + occurrences
  POST /entities/admin/merge            — merge source into target
  POST /entities/admin/reindex/{slug}   — full re-index of a collection
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.collection import Collection
from app.plugins._native.named_entities import service
from app.plugins._native.named_entities.models import EntityType
from app.plugins._native.named_entities.schemas import (
    EntityMergeRequest,
    EntityOccurrenceResponse,
    NamedEntityResponse,
    NamedEntityUpdate,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/entities", tags=["named-entities"])

_DbDep = Annotated[AsyncSession, Depends(get_async_session)]
_ExistDep = Annotated[ExistDBClient, Depends(get_existdb)]
_AdminDep = Annotated[None, Depends(require_role(min_role="Admin"))]


def _paginate(items: list, total: int, page: int, per_page: int) -> PaginatedResponse:
    import math
    return PaginatedResponse(
        data=items,
        pagination=PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ),
    )


# ── Admin routes (declared first to avoid conflict with /{entity_id}) ─────────

@router.get("/admin")
async def admin_list_entities(
    _: _AdminDep,
    db: _DbDep,
    entity_type: Annotated[EntityType | None, Query(alias="type")] = None,
    q: str | None = None,
    unlinked: bool = False,
    page: int = 1,
    per_page: int = 30,
) -> PaginatedResponse:
    """Admin: list all named entities regardless of collection visibility."""
    rows, total = await service.get_admin_entities(
        db, entity_type, q, unlinked, page, per_page
    )
    return _paginate([NamedEntityResponse.model_validate(r) for r in rows], total, page, per_page)


@router.post("/admin/merge")
async def admin_merge_entities(
    body: EntityMergeRequest,
    _: _AdminDep,
    db: _DbDep,
) -> DataResponse[NamedEntityResponse]:
    """Admin: merge source entity into target (source is deleted)."""
    target = await service.merge_entities(db, body.source_id, body.target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="One or both entities not found")
    await db.commit()
    return DataResponse(data=NamedEntityResponse.model_validate(target))


@router.post("/admin/reindex/{collection_slug}")
async def admin_reindex_collection(
    collection_slug: str,
    _: _AdminDep,
    db: _DbDep,
    existdb: _ExistDep,
) -> DataResponse[dict]:
    """Admin: wipe and rebuild the entity index for an entire collection."""
    col = await db.scalar(select(Collection).where(Collection.slug == collection_slug))
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    total = await service.reindex_collection(db, existdb, col)
    return DataResponse(data={"collection_slug": collection_slug, "occurrences_indexed": total})


@router.put("/admin/{entity_id}")
async def admin_update_entity(
    entity_id: uuid.UUID,
    body: NamedEntityUpdate,
    _: _AdminDep,
    db: _DbDep,
) -> DataResponse[NamedEntityResponse]:
    """Admin: update canonical_form and/or authority_ref of an entity."""
    entity = await service.update_entity(
        db, entity_id, body.canonical_form, body.authority_ref
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    await db.commit()
    return DataResponse(data=NamedEntityResponse.model_validate(entity))


@router.delete("/admin/{entity_id}", status_code=204)
async def admin_delete_entity(
    entity_id: uuid.UUID,
    _: _AdminDep,
    db: _DbDep,
) -> None:
    """Admin: permanently delete an entity and all its occurrences."""
    deleted = await service.delete_entity(db, entity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entity not found")
    await db.commit()


# ── Public routes ─────────────────────────────────────────────────────────────

@router.get("")
async def list_entities(
    db: _DbDep,
    entity_type: Annotated[EntityType | None, Query(alias="type")] = None,
    q: str | None = None,
    page: int = 1,
    per_page: int = 30,
) -> PaginatedResponse:
    """Public: paginated list of named entities from published public collections."""
    rows, total = await service.get_public_entities(db, entity_type, q, page, per_page)
    return _paginate([NamedEntityResponse.model_validate(r) for r in rows], total, page, per_page)


@router.get("/{entity_id}/occurrences")
async def list_entity_occurrences(
    entity_id: uuid.UUID,
    db: _DbDep,
    collection: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> PaginatedResponse:
    """Public: paginated occurrences of one entity in published public collections."""
    rows, total = await service.get_entity_occurrences(
        db,
        entity_id,
        public_only=True,
        collection_slug=collection,
        page=page,
        per_page=per_page,
    )
    return _paginate(
        [EntityOccurrenceResponse(**r) for r in rows], total, page, per_page
    )
