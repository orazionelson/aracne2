"""Abstract base + event types for the tool-use provider adapters.

Both providers (Ollama, Anthropic) yield the same flat event stream
so the orchestrator's loop is provider-agnostic. The orchestrator
drives the conversation: it consumes one ``run_round`` invocation per
LLM round-trip, collects the tool-call requests it emits, dispatches
them through the MCP tool layer, and feeds the results back as the
next ``run_round`` input.

We deliberately do **not** inherit from the existing
``app.plugins._native.ai.providers.base.BaseAiProvider`` — that ABC
yields plain text chunks for the editor's free-form AI panel and has
no notion of tool calls. Conflating the two would force every existing
provider to learn tool-use, and we'd lose the simple text-streaming
shape the editor relies on.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TextChunk:
    """Delta of model-emitted text. Concatenate as it arrives."""

    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """The model is asking the platform to run a tool.

    ``id`` is the provider-supplied correlation token; the orchestrator
    must echo it back when feeding the tool result.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    """Token counters reported by the provider for one round.

    Cloud providers (Anthropic / OpenAI) populate both fields; Ollama
    leaves them at 0 — local inference has no $ cost so the budget
    layer never reads these for an ``ollama`` provider.
    """

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Done:
    """Terminal event emitted at the end of every round.

    ``stop_reason``:

    - ``"end_turn"`` — model produced a final answer; orchestrator
      stops looping.
    - ``"tool_use"`` — model wants to call tools; orchestrator runs
      every ``ToolCallRequest`` event seen this round and starts a
      new round with the tool results appended to the conversation.
    - ``"max_tokens"`` / ``"stop_sequence"`` / others — orchestrator
      stops looping and surfaces whatever text accumulated so far.

    ``usage`` carries the round's token counters (zeros for Ollama).
    """

    stop_reason: str
    usage: Usage = field(default_factory=Usage)


class ProviderError(RuntimeError):
    """Raised when the provider cannot complete a round.

    HTTP-level failures (timeout, 5xx, malformed JSON, …) all bubble
    up as this single class so the orchestrator's error path is
    uniform across providers.
    """


# Event union — every provider yields one of these.
ProviderEvent = TextChunk | ToolCallRequest | Done


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool advertised to the model.

    The shape mirrors Anthropic's Messages API tool schema; the Ollama
    adapter translates to the OpenAI-compatible function-call shape.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a tool invocation, fed back to the model next round.

    ``content`` is a JSON-encodable Python object; the adapter
    serialises it with ``ensure_ascii=False`` so non-ASCII text in
    document bodies survives the round-trip.
    """

    tool_call_id: str
    content: Any
    is_error: bool = False


class ToolUseProvider(ABC):
    """Tool-use streaming adapter — one method, ``run_round``."""

    @abstractmethod
    def run_round(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[ToolDescriptor],
        timeout_s: float,
    ) -> AsyncGenerator[ProviderEvent, None]:
        """Execute one LLM round-trip and yield events as they arrive.

        ``messages`` is the full conversation so far in the provider's
        wire format (the orchestrator builds it via the helper
        :func:`build_messages` documented per adapter). ``tools`` is
        the manifest of tools the model is allowed to call. ``timeout_s``
        is the per-round wall-clock cap.

        Implementations MUST yield exactly one :class:`Done` event
        as their last yield, regardless of failure mode (a
        :class:`ProviderError` may be raised instead, in which case
        no ``Done`` is required).
        """
        raise NotImplementedError
        # required by AsyncGenerator typing
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
