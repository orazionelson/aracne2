"""Abstract base class for AI provider streaming adapters."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseAiProvider(ABC):
    """Each provider subclass wraps one LLM API and yields text chunks."""

    @abstractmethod
    async def stream(self, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        """Yield text chunks as they arrive from the provider.

        ``messages`` is a list of ``{"role": "user"|"assistant", "content": "..."}``
        dicts representing the full conversation so far.  The first entry is always
        the resolved prompt template (role ``user``); any subsequent entries carry
        the chat history for multi-turn conversations.

        The generator must be fully consumed or explicitly closed by the caller.
        Implementations should raise httpx.HTTPStatusError on provider errors
        so the service layer can surface a consistent error message.
        """
        # Required by ABC but never reached — the yield makes this a generator.
        yield  # type: ignore[misc]
