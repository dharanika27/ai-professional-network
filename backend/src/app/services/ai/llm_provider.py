"""LLMProvider interface — the single contract every LLM call depends on.

Callers (LLMClient, feature services) import ONLY this Protocol. The concrete
provider (GroqProvider) is wired at startup and injected; no caller ever imports
a concrete provider or the underlying SDK.

Amendment 001: the LLM provider is Groq, but nothing here mentions Groq — the
whole point of this interface is provider-independence. No SDK import lives here.

No import of `groq`, any external LLM SDK, fastapi, or any repository/db module.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic chat-completion interface.

    A provider translates a normalized request (messages + generation params)
    into a call against a concrete LLM backend and returns raw text plus token
    usage. Structured-output enforcement, retries, and logging are NOT the
    provider's concern — those live in LLMClient.
    """

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        response_format: dict[str, str] | None,
        timeout: float,
    ) -> tuple[str, int, int]:
        """Perform a single blocking chat completion.

        Args:
            messages: OpenAI-style ``[{"role": ..., "content": ...}]`` list.
            model: Provider model identifier.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            response_format: Optional structured-output hint, e.g.
                ``{"type": "json_object"}``. ``None`` for free-form text.
            timeout: Per-request timeout in seconds. Non-retryable on expiry.

        Returns:
            A ``(text, input_tokens, output_tokens)`` tuple. ``text`` is the raw
            assistant message content; token counts are provider-reported usage.

        Raises:
            AIProviderError: On any backend/transport failure.
            AITimeoutError: When the request exceeds ``timeout`` seconds.
        """
        ...

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Iterator[str]:
        """Stream a chat completion as incremental text deltas.

        Args:
            messages: OpenAI-style message list.
            model: Provider model identifier.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            timeout: Per-request timeout in seconds.

        Yields:
            Text delta strings in arrival order. Concatenating all yielded
            deltas reconstructs the full assistant message.

        Raises:
            AIProviderError: On any backend/transport failure.
            AITimeoutError: When the request exceeds ``timeout`` seconds.
        """
        ...
