"""AI integration service — rate limiting, template filling, provider dispatch."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, ExternalServiceError, PlatformException
from app.models.ai_prompt import AiPrompt
from app.models.ai_request_log import AiRequestLog
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.plugins._native.ai.providers.base import BaseAiProvider
from app.schemas.ai import AiConfigResponse, AiPromptResponse
from app.services.settings import get_decrypted_setting

logger = structlog.get_logger()


class AiDisabledError(PlatformException):
    def __init__(self) -> None:
        super().__init__(
            code="AI_PROVIDER_DISABLED",
            message="AI provider is not configured. Set ai_provider in Settings.",
            status_code=503,
        )


class AiRateLimitError(PlatformException):
    def __init__(self, limit: int) -> None:
        super().__init__(
            code="AI_RATE_LIMIT_EXCEEDED",
            message=f"AI rate limit exceeded: {limit} requests per hour.",
            status_code=429,
        )


# ── Prompt helpers ─────────────────────────────────────────────────────────────

async def list_prompts(
    db: AsyncSession, target_context: str | None = None
) -> list[AiPromptResponse]:
    q = select(AiPrompt).order_by(AiPrompt.label)
    if target_context:
        q = q.where(
            (AiPrompt.target_context == target_context) | AiPrompt.target_context.is_(None)
        )
    rows = await db.scalars(q)
    return [AiPromptResponse.model_validate(r) for r in rows]


async def get_prompt(db: AsyncSession, slug: str) -> AiPrompt:
    row = await db.scalar(select(AiPrompt).where(AiPrompt.slug == slug))
    if not row:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(f"AI prompt '{slug}' not found")
    return row


async def create_prompt(
    db: AsyncSession, data: "AiPromptCreate"  # type: ignore[name-defined]
) -> AiPromptResponse:
    from app.core.exceptions import ConflictError
    existing = await db.scalar(select(AiPrompt).where(AiPrompt.slug == data.slug))
    if existing:
        raise ConflictError(f"Prompt with slug '{data.slug}' already exists")
    prompt = AiPrompt(**data.model_dump())
    db.add(prompt)
    await db.flush()
    return AiPromptResponse.model_validate(prompt)


async def update_prompt(
    db: AsyncSession, slug: str, data: "AiPromptUpdate"  # type: ignore[name-defined]
) -> AiPromptResponse:
    prompt = await get_prompt(db, slug)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prompt, field, value)
    prompt.updated_at = datetime.now(UTC)
    await db.flush()
    return AiPromptResponse.model_validate(prompt)


async def delete_prompt(db: AsyncSession, slug: str) -> None:
    prompt = await get_prompt(db, slug)
    if prompt.is_native:
        raise DomainValidationError(
            "AI_PROMPT_NATIVE",
            "Native prompts cannot be deleted. You can edit their template instead.",
        )
    await db.delete(prompt)
    await db.flush()


# ── Config helper ──────────────────────────────────────────────────────────────

async def get_ai_config(db: AsyncSession) -> AiConfigResponse:
    provider_row = await db.get(SystemSetting, "ai_provider")
    provider_name = provider_row.value if provider_row else "disabled"

    model_row = await db.get(SystemSetting, f"ai_{provider_name}_model")
    model_name = model_row.value if model_row else ""

    rate_row = await db.get(SystemSetting, "ai_max_requests_per_hour")
    rate_limit = int(rate_row.value) if rate_row else 20

    privacy_row = await db.get(SystemSetting, "ai_privacy_warning_enabled")
    privacy = (privacy_row.value == "true") if privacy_row else False

    return AiConfigResponse(
        provider=provider_name,
        model=model_name,
        rate_limit=rate_limit,
        privacy_warning=privacy,
    )


# ── Provider factory ───────────────────────────────────────────────────────────

async def _get_provider(db: AsyncSession) -> BaseAiProvider:
    """Read settings and instantiate the configured AI provider."""
    provider_row = await db.get(SystemSetting, "ai_provider")
    provider_name = provider_row.value if provider_row else "disabled"

    if provider_name == "disabled":
        raise AiDisabledError()

    api_key = await get_decrypted_setting(db, f"ai_{provider_name}_api_key")
    if not api_key:
        raise AiDisabledError()

    model_row = await db.get(SystemSetting, f"ai_{provider_name}_model")
    model = model_row.value if model_row else ""

    if provider_name == "openai":
        from app.plugins._native.ai.providers.openai import OpenAiProvider
        return OpenAiProvider(api_key=api_key, model=model)
    if provider_name == "anthropic":
        from app.plugins._native.ai.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=model)
    if provider_name == "gemini":
        from app.plugins._native.ai.providers.gemini import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model)

    raise AiDisabledError()


# ── Rate limiting ──────────────────────────────────────────────────────────────

async def _check_rate_limit(db: AsyncSession, user: User) -> int:
    """Return the hourly limit; raise AiRateLimitError if exceeded."""
    rate_row = await db.get(SystemSetting, "ai_max_requests_per_hour")
    limit = int(rate_row.value) if rate_row else 20

    since = datetime.now(UTC) - timedelta(hours=1)
    count = await db.scalar(
        select(func.count(AiRequestLog.id)).where(
            AiRequestLog.user_id == user.id,
            AiRequestLog.created_at >= since,
        )
    )
    if (count or 0) >= limit:
        raise AiRateLimitError(limit)
    return limit


# ── Main streaming entry point ─────────────────────────────────────────────────

def _fill_template(template: str, context: dict[str, str]) -> str:
    """Substitute {variables} in *template* using *context*.

    Raises DomainValidationError for missing variables.
    """
    try:
        return template.format_map(context)
    except KeyError as exc:
        raise DomainValidationError(
            "AI_MISSING_CONTEXT_VAR",
            f"Missing required context variable: {exc}",
        )


async def stream_completion(
    db: AsyncSession,
    prompt_slug: str,
    context: dict[str, str],
    user: User,
) -> AsyncGenerator[str, None]:
    """Rate-limit, fill the prompt template, call the provider, yield chunks."""
    await _check_rate_limit(db, user)

    prompt = await get_prompt(db, prompt_slug)
    filled = _fill_template(prompt.template, context)

    provider_row = await db.get(SystemSetting, "ai_provider")
    provider_name: str = provider_row.value if provider_row else "disabled"

    provider = await _get_provider(db)

    # Log the request before streaming starts (counts toward rate limit).
    db.add(
        AiRequestLog(
            user_id=user.id,
            prompt_slug=prompt_slug,
            provider=provider_name,
        )
    )
    await db.commit()

    logger.info(
        "ai_stream_start",
        user_id=str(user.id),
        prompt_slug=prompt_slug,
        provider=provider_name,
    )

    try:
        async for chunk in provider.stream(filled):
            yield chunk
    except httpx.HTTPStatusError as exc:
        raise ExternalServiceError(
            provider_name,
            f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        )
    except httpx.RequestError as exc:
        raise ExternalServiceError(provider_name, str(exc))
