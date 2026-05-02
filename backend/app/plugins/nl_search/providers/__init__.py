"""Tool-use provider adapters for the natural-language search plugin.

Two providers are shipped today:

- :class:`OllamaToolUseProvider` — local, no $ cost, default for the
  spec-recommended safe-posture configuration.
- :class:`AnthropicToolUseProvider` — cloud, billed; opt-in via
  ``nl_search_provider=anthropic`` + ``nl_search_api_key``.

Both implement :class:`ToolUseProvider` and exchange the same
:mod:`events` envelope so the orchestrator stays provider-agnostic.
The factory :func:`make_provider` reads ``system_settings`` and
returns the configured adapter.
"""

from app.plugins.nl_search.providers.base import (
    Done,
    ProviderError,
    TextChunk,
    ToolCallRequest,
    ToolUseProvider,
    Usage,
)
from app.plugins.nl_search.providers.factory import make_provider

__all__ = [
    "Done",
    "ProviderError",
    "TextChunk",
    "ToolCallRequest",
    "ToolUseProvider",
    "Usage",
    "make_provider",
]
