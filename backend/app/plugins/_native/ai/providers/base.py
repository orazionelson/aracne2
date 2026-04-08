"""Abstract base class for AI provider streaming adapters."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseAiProvider(ABC):
    """Each provider subclass wraps one LLM API and yields text chunks."""

    @abstractmethod
    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Yield text chunks as they arrive from the provider.

        The generator must be fully consumed or explicitly closed by the caller.
        Implementations should raise httpx.HTTPStatusError on provider errors
        so the service layer can surface a consistent error message.
        """
        # Required by ABC but never reached — the yield makes this a generator.
        yield  # type: ignore[misc]
