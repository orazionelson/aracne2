"""AI integration router — prompt library CRUD and streaming completion."""

import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_async_session
from app.middleware.acl import require_role
from app.models.user import User
from app.plugins._native.ai import service
from app.core.exceptions import ExternalServiceError
from app.plugins._native.ai.service import AiDisabledError, AiRateLimitError
from app.schemas.ai import (
    AiCompleteRequest,
    AiConfigResponse,
    AiPromptCreate,
    AiPromptResponse,
    AiPromptUpdate,
)
from app.schemas.common import DataResponse

router = APIRouter(prefix="/ai", tags=["ai"])

_editor = Depends(require_role(min_role="Editor"))
_admin = Depends(require_role(min_role="Admin"))


# ── Prompt library ─────────────────────────────────────────────────────────────

@router.get("/prompts")
async def ai_prompts_list(
    current_user: Annotated[User, _editor],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    scope: Annotated[str | None, Query()] = None,
) -> DataResponse[list[AiPromptResponse]]:
    """List AI prompt templates, optionally filtered by scope [E+]."""
    data = await service.list_prompts(db, scope=scope)
    return DataResponse(data=data)


@router.post("/prompts")
async def ai_prompt_create(
    body: AiPromptCreate,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[AiPromptResponse]:
    """Create a custom AI prompt template [Admin]."""
    data = await service.create_prompt(db, body)
    await db.commit()
    return DataResponse(data=data)


@router.patch("/prompts/{slug}")
async def ai_prompt_update(
    slug: str,
    body: AiPromptUpdate,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[AiPromptResponse]:
    """Update an AI prompt template [Admin]."""
    data = await service.update_prompt(db, slug, body)
    await db.commit()
    return DataResponse(data=data)


@router.delete("/prompts/{slug}", status_code=204)
async def ai_prompt_delete(
    slug: str,
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Delete a custom AI prompt (native prompts cannot be deleted) [Admin]."""
    await service.delete_prompt(db, slug)
    await db.commit()


# ── Config ─────────────────────────────────────────────────────────────────────

@router.get("/config")
async def ai_config(
    current_user: Annotated[User, _admin],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> DataResponse[AiConfigResponse]:
    """Return the current AI configuration (provider, model, rate limit) [Admin]."""
    data = await service.get_ai_config(db)
    return DataResponse(data=data)


# ── Streaming completion ───────────────────────────────────────────────────────

@router.post("/complete")
async def ai_complete(
    body: AiCompleteRequest,
    current_user: Annotated[User, _editor],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> StreamingResponse:
    """Stream an AI completion for the given prompt slug and context [E+].

    Response format: Server-Sent Events (text/event-stream).
    Each event: ``data: {"chunk": "..."}\\n\\n``
    Terminal event: ``data: [DONE]\\n\\n``
    Error event: ``data: {"error": "..."}\\n\\n`` followed by ``[DONE]``
    """

    # Check rate limit before the StreamingResponse is created so we can return
    # a proper 429 status code instead of embedding the error in an SSE body.
    try:
        await service._check_rate_limit(db, current_user)
    except AiRateLimitError as exc:
        raise HTTPException(status_code=429, detail=exc.message)

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in service.stream_completion(
                db, body.prompt_slug, body.context, current_user, body.history or None
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except AiDisabledError as exc:
            yield f"data: {json.dumps({'error': exc.message})}\n\n"
        except ExternalServiceError as exc:
            detail: str = exc.details.get("detail") or exc.message  # type: ignore[assignment]
            yield f"data: {json.dumps({'error': detail})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
