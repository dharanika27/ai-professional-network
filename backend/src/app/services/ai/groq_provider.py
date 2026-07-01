"""GroqProvider — the ONLY module that imports the groq SDK.

Concrete ``LLMProvider`` implementation backed by Groq chat completions
(Amendment 001). Every other module depends on the ``LLMProvider`` protocol,
never on this class or on ``groq`` directly.

The ``groq`` import is deferred to call time so that:
  * modules importing the protocol never pay the SDK import cost, and
  * unit tests (which inject a mock provider) run without the SDK installed.

The API key is injected via the constructor — this module NEVER reads the
environment directly.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

from app.services.ai.llm_client import AIProviderError, AITimeoutError

logger = logging.getLogger(__name__)

# A synthetic request id used when a provider-level failure occurs outside any
# client-supplied correlation id. The LLMClient re-wraps errors with the real
# request_id, so this is only a placeholder for direct provider usage/tests.
_UNKNOWN_REQUEST = uuid.UUID(int=0)


class GroqProvider:
    """Groq-backed implementation of the LLMProvider protocol."""

    def __init__(self, api_key: str | None) -> None:
        """Store the injected API key. The SDK client is built lazily.

        Args:
            api_key: Groq API key. Injected — never read from the environment here.
        """
        self._api_key = api_key
        # Typed as Any at the SDK boundary: this wrapper deliberately does not
        # couple the rest of the app to groq's concrete client/param types.
        self._client: Any = None

    def _get_client(self) -> Any:
        """Build (once) and return the groq SDK client. Imports ``groq`` lazily."""
        if self._client is None:
            from groq import Groq  # deferred: only place `groq` is imported

            self._client = Groq(api_key=self._api_key)
        return self._client

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        response_format: dict[str, str] | None,
        timeout: float,
    ) -> tuple[str, int, int]:
        """Perform a single Groq chat completion.

        Returns:
            ``(text, input_tokens, output_tokens)``.

        Raises:
            AITimeoutError: The request exceeded ``timeout`` seconds.
            AIProviderError: Any other Groq/transport failure. The message is a
                safe generic string — no raw payload or PII.
        """
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "messages": messages,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": timeout,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            completion = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — normalized into typed AI errors
            raise self._normalize_error(exc) from None

        text = completion.choices[0].message.content or ""
        usage = completion.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return text, input_tokens, output_tokens

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Iterator[str]:
        """Stream a Groq chat completion as text deltas.

        Yields:
            Incremental content strings; empty deltas are skipped.

        Raises:
            AITimeoutError: The request exceeded ``timeout`` seconds.
            AIProviderError: Any other Groq/transport failure.
        """
        client = self._get_client()
        try:
            stream = client.chat.completions.create(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # noqa: BLE001 — normalized into typed AI errors
            raise self._normalize_error(exc) from None

    @staticmethod
    def _normalize_error(exc: Exception) -> AIProviderError | AITimeoutError:
        """Map an arbitrary SDK/transport error to a safe typed AI error.

        Timeout-shaped errors become ``AITimeoutError`` (non-retryable upstream);
        everything else becomes a generic ``AIProviderError``. The original
        message is NOT propagated to avoid leaking payloads.
        """
        name = type(exc).__name__.lower()
        if "timeout" in name or isinstance(exc, TimeoutError):
            return AITimeoutError(_UNKNOWN_REQUEST)
        return AIProviderError("Groq provider call failed", _UNKNOWN_REQUEST)
