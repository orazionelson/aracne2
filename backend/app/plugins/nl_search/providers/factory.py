"""Provider factory — reads ``system_settings`` and returns the adapter.

Called once per request from the orchestrator. The factory also
loads the system prompt for the requesting language (Anthropic
requires the system prompt at the message-API level; Ollama receives
it as the first ``role: system`` message and the orchestrator
prepends it there).
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings import get_decrypted_setting

from app.plugins.nl_search.providers.anthropic import AnthropicToolUseProvider
from app.plugins.nl_search.providers.base import ProviderError, ToolUseProvider
from app.plugins.nl_search.providers.ollama import OllamaToolUseProvider


_DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")


async def make_provider(
    db: AsyncSession, *, system_prompt: str
) -> ToolUseProvider:
    """Build the configured provider, raising on misconfiguration.

    Decisions:

    - Empty / unknown ``nl_search_provider`` → fall back to Ollama at
      the default host so a deployment without an API key still has a
      working code path. The Admin sees a clear error in their logs;
      the public endpoint returns 503 if the server is unreachable.
    - Anthropic without an API key → :class:`ProviderError`. The
      endpoint surfaces this as a 503 ``PROVIDER_MISCONFIGURED`` so
      the operator can fix Settings before retrying.
    """
    provider = (
        await get_decrypted_setting(db, "nl_search_provider") or "ollama"
    ).strip().lower()
    model = (
        await get_decrypted_setting(db, "nl_search_model")
    ).strip() or _default_model_for(provider)

    if provider == "anthropic":
        api_key = (
            await get_decrypted_setting(db, "nl_search_api_key")
        ).strip()
        if not api_key:
            raise ProviderError(
                "Anthropic provider selected but nl_search_api_key is empty."
            )
        return AnthropicToolUseProvider(
            api_key=api_key, model=model, system_prompt=system_prompt
        )

    # Default / Ollama branch
    return OllamaToolUseProvider(host=_DEFAULT_OLLAMA_HOST, model=model)


def _default_model_for(provider: str) -> str:
    """Per-provider default model when ``nl_search_model`` is empty."""
    if provider == "anthropic":
        return "claude-sonnet-4-6"
    return "llama3.1"
