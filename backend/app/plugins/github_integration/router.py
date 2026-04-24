"""Github plugin — HTTP router.

Mounted at ``/api/v1/plugins/github``. ACL split:

- ``/config`` — Admin only (manages the global PAT).
- ``/collections/{slug}/link`` + ``/push`` — EditorInChief and above
  (editors who orchestrate publication pipelines).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ROLE_LEVEL
from app.core.exceptions import AuthorizationError, DomainValidationError
from app.db.existdb import ExistDBClient, get_existdb
from app.db.postgres import get_async_session
from app.dependencies import get_current_user
from app.middleware.acl import require_role
from app.models.user import User
from app.plugins.github_integration import service
from app.plugins.github_integration.schemas import (
    GithubConfig,
    GithubConfigUpdate,
    GithubInitializeResponse,
    GithubLinkCreate,
    GithubLinkResponse,
    GithubPushRequest,
    GithubPushResponse,
    GithubWebsiteLinkCreate,
    GithubWebsiteLinkResponse,
    GithubWebsitePushRequest,
    GithubWebsitePushResponse,
)
from app.schemas.common import DataResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/plugins/github", tags=["github"])

_admin = Depends(require_role(min_role="Admin"))
_eic = Depends(require_role(min_role="EditorInChief"))


async def _require_designer_plus(
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> User:
    """Website-side ACL: Designer, EditorInChief, or Admin.

    Mirrors the ``DesignerPlus`` dependency in
    ``app/routers/websites.py`` — keep the two definitions aligned if
    the project changes its role model.
    """
    role: str = getattr(request.state, "role", "User")
    user_level = ROLE_LEVEL.get(role, 0)
    if role != "Designer" and user_level < ROLE_LEVEL["EditorInChief"]:
        raise AuthorizationError()
    return user


_designer_plus = Depends(_require_designer_plus)


# ── Config ─────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config(
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubConfig]:
    return DataResponse(
        data=GithubConfig(pat_set=await service.get_config_pat_set(db)),
    )


@router.put("/config")
async def update_config(
    body: GithubConfigUpdate,
    _: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubConfig]:
    await service.update_config_pat(db, body.pat)
    await db.commit()
    return DataResponse(
        data=GithubConfig(pat_set=await service.get_config_pat_set(db)),
    )


# ── Link CRUD ──────────────────────────────────────────────────────────────


@router.get("/collections/{slug}/link")
async def read_link(
    slug: str,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubLinkResponse]:
    return DataResponse(data=await service.get_link(db, slug))


@router.put("/collections/{slug}/link")
async def write_link(
    slug: str,
    body: GithubLinkCreate,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubLinkResponse]:
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
    body: GithubPushRequest,
    _: Annotated[User, _eic],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    existdb: Annotated[ExistDBClient, Depends(get_existdb)],
) -> DataResponse[GithubPushResponse]:
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
) -> DataResponse[GithubInitializeResponse]:
    """One-shot import: copy every XML file from the linked Github
    repo into the *empty* Aracne2 collection.

    Refuses (409) when the collection already has any documents or
    when the link has already been initialized. After a successful
    initialize the only allowed direction is push (Aracne2 → forge).
    """
    result = await service.initialize_collection(db, existdb, slug=slug)
    await db.commit()
    return DataResponse(data=result)


# ── Website link CRUD + push ───────────────────────────────────────────────


@router.get("/websites/{slug}/link")
async def read_website_link(
    slug: str,
    _: Annotated[User, _designer_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubWebsiteLinkResponse]:
    return DataResponse(data=await service.get_website_link(db, slug))


@router.put("/websites/{slug}/link")
async def write_website_link(
    slug: str,
    body: GithubWebsiteLinkCreate,
    _: Annotated[User, _designer_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubWebsiteLinkResponse]:
    result = await service.upsert_website_link(db, slug, body)
    await db.commit()
    return DataResponse(data=result)


@router.delete("/websites/{slug}/link", status_code=204)
async def delete_website_link(
    slug: str,
    _: Annotated[User, _designer_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    await service.delete_website_link(db, slug)
    await db.commit()


@router.post("/websites/{slug}/push")
async def push_website(
    slug: str,
    body: GithubWebsitePushRequest,
    _: Annotated[User, _designer_plus],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[GithubWebsitePushResponse]:
    """Push the rendered static output of ``slug`` to its linked
    Github repository in a single commit.

    Requires the website to have been built (``build_status=done``)
    and the rendering mode to be STATIC or HYBRID. A DYNAMIC site
    produces nothing on disk and returns 409.
    """
    result = await service.push_website(
        db, slug=slug, message=body.message,
    )
    await db.commit()
    return DataResponse(data=result)
