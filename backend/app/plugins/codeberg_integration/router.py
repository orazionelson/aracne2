"""Codeberg plugin — HTTP router.

Mounted at ``/api/v1/plugins/codeberg``. ACL split:

- ``/config`` — Admin only (manages the global PAT).
- ``/collections/{slug}/link`` + ``/push`` — EditorInChief and above
  (editors who orchestrate publication pipelines).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError
from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.plugins.codeberg_integration import service
from app.plugins.codeberg_integration.schemas import (
    CodebergConfig,
    CodebergConfigUpdate,
    CodebergInitializeResponse,
    CodebergLinkCreate,
    CodebergLinkResponse,
    CodebergPushRequest,
    CodebergPushResponse,
)
from app.schemas.common import DataResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/plugins/codeberg", tags=["codeberg"])

_admin = Depends(require_role(min_role="Admin"))
_eic = Depends(require_role(min_role="EditorInChief"))


# ── Config ─────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config(
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CodebergConfig]:
    return DataResponse(
        data=CodebergConfig(pat_set=await service.get_config_pat_set(db)),
    )


@router.put("/config")
async def update_config(
    body: CodebergConfigUpdate,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CodebergConfig]:
    await service.update_config_pat(db, body.pat)
    await db.commit()
    return DataResponse(
        data=CodebergConfig(pat_set=await service.get_config_pat_set(db)),
    )


# ── Link CRUD ──────────────────────────────────────────────────────────────


@router.get("/collections/{slug}/link")
async def read_link(
    slug: str,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CodebergLinkResponse]:
    return DataResponse(data=await service.get_link(db, slug))


@router.put("/collections/{slug}/link")
async def write_link(
    slug: str,
    body: CodebergLinkCreate,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[CodebergLinkResponse]:
    result = await service.upsert_link(db, slug, body)
    await db.commit()
    return DataResponse(data=result)


@router.delete("/collections/{slug}/link", status_code=204)
async def delete_link(
    slug: str,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await service.delete_link(db, slug)
    await db.commit()


# ── Push ───────────────────────────────────────────────────────────────────


@router.post("/collections/{slug}/push")
async def push_collection(
    slug: str,
    body: CodebergPushRequest,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[CodebergPushResponse]:
    try:
        result = await service.push_collection(
            db, existdb, slug=slug, message=body.message,
        )
    except DomainValidationError:
        # Let the global handler translate to HTTP with the domain code.
        raise
    await db.commit()
    return DataResponse(data=result)


# ── Initialize ─────────────────────────────────────────────────────────────


@router.post("/collections/{slug}/initialize")
async def initialize_collection(
    slug: str,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[CodebergInitializeResponse]:
    """One-shot import: copy every XML file from the linked Codeberg
    repo into the *empty* Aracne2 collection.

    Refuses (409) when the collection already has any documents or
    when the link has already been initialized. After a successful
    initialize the only allowed direction is push (Aracne2 → forge).
    """
    result = await service.initialize_collection(db, existdb, slug=slug)
    await db.commit()
    return DataResponse(data=result)
