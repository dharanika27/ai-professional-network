"""LLMClient — the provider-agnostic orchestration chokepoint for all AI calls.

Every AI feature (resume structuring, resume review, profile optimization, job
matching) goes through this client. It owns the invariants that the rest of the
codebase relies on:

  * Structured output is a HARD requirement. ``complete_structured`` asks the
    provider for JSON-constrained output, then validates it with
    ``schema.model_validate(...)``. Raw LLM text is NEVER returned to callers.
  * On invalid JSON / schema failure → exactly ONE retry → safe typed error.
    At most two provider calls per request.
  * A 60s (config) timeout is non-retryable and surfaces as ``AITimeoutError``.
  * Exactly one metadata-only ``ai_request_logs`` row is written per call.
    Prompt text, resume text, emails, filenames, and other PII are NEVER logged
    and NEVER placed in exception messages.

Depends only on the ``LLMProvider`` Protocol — never a concrete provider, never
the groq SDK. No fastapi import.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.repositories import ai_log_repository
from app.services.ai.llm_provider import LLMProvider
from app.types.enums import AIFeature, AIOutcome

if TYPE_CHECKING:
    from app.config.llm_config import LLMConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Typed error hierarchy (safe — never carry raw provider text or PII)
# ---------------------------------------------------------------------------


class AISchemaError(Exception):
    """Raised when the provider output fails schema validation after retry.

    The message is intentionally generic — it never contains raw provider
    text, prompt content, or PII. The ``request_id`` correlates with the
    ``ai_request_logs`` row for debugging.
    """

    def __init__(self, message: str, request_id: uuid.UUID) -> None:
        super().__init__(message)
        self.request_id = request_id


class AIProviderError(Exception):
    """Raised on a provider/transport failure that is not a timeout.

    The message is a safe, generic description — no raw provider payload.
    """

    def __init__(self, message: str, request_id: uuid.UUID) -> None:
        super().__init__(message)
        self.request_id = request_id


class AITimeoutError(Exception):
    """Raised when a provider call exceeds the configured timeout.

    Timeouts are non-retryable. The message is fixed and PII-free.
    """

    def __init__(self, request_id: uuid.UUID) -> None:
        super().__init__("AI request timed out")
        self.request_id = request_id


# ---------------------------------------------------------------------------
# Per-feature task profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TaskProfile:
    """Resolved generation parameters for one AIFeature."""

    model: str
    max_tokens: int
    temperature: float


# ---------------------------------------------------------------------------
# Streaming event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamEvent:
    """One event emitted by ``stream_structured``.

    ``kind == "delta"``  → ``text`` holds an incremental text chunk, ``data`` None.
    ``kind == "result"`` → ``data`` holds the validated schema instance, ``text`` None.
    """

    kind: Literal["delta", "result"]
    text: str | None = None
    data: BaseModel | None = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LLMClient:
    """Orchestrates structured LLM calls with retry, timeout, and metadata logging."""

    def __init__(
        self,
        provider: LLMProvider,
        config: LLMConfig,
        ai_log_repo: object,
        db_session_factory: Callable[[], Session],
    ) -> None:
        """Wire the client.

        Args:
            provider: Any object satisfying the LLMProvider protocol.
            config: Immutable LLM configuration (models, tokens, timeout, retries).
            ai_log_repo: The metadata-only log-writer module/object. Accepted for
                dependency injection; the module ``ai_log_repository`` is used
                directly for its ``log_request`` function.
            db_session_factory: Zero-arg callable returning a new Session. Used to
                open a short-lived session for the single log write, isolated from
                any request transaction so logging never rolls back business work.
        """
        self._provider = provider
        self._config = config
        self._ai_log_repo = ai_log_repo
        self._db_session_factory = db_session_factory

    # -- public API --------------------------------------------------------

    def complete_structured(
        self,
        feature: AIFeature,
        system: str,
        user_blocks: list[str],
        schema: type[T],
        request_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> T:
        """Request JSON-constrained output and return a validated ``schema`` instance.

        Performs at most two provider calls: an initial attempt plus (on invalid
        JSON or schema-validation failure) exactly one retry. On the first attempt
        succeeding, ``retry_count == 0`` and outcome ``success``. On a retry
        succeeding, ``retry_count == 1`` and outcome ``retry_success``.

        Args:
            feature: Which AI feature is calling — selects model/tokens/temperature.
            system: System prompt (no PII beyond what the caller controls; never logged).
            user_blocks: Already-delimited user content blocks; joined into one message.
            schema: A Pydantic model subclass to validate the output against.
            request_id: Correlation id, written to the log row.
            user_id: Optional owning user id, written to the log row.

        Returns:
            A validated instance of ``schema``. Never raw text.

        Raises:
            AITimeoutError: The provider timed out (non-retryable).
            AISchemaError: Output failed JSON parse/schema validation after the retry.
            AIProviderError: The provider failed after the retry.
        """
        profile = self._resolve_profile(feature)
        messages = self._build_messages(system, user_blocks)
        started = time.monotonic()

        last_input_tokens: int | None = None
        last_output_tokens: int | None = None

        for attempt in range(self._max_attempts()):
            try:
                text, in_tok, out_tok = self._provider.complete(
                    messages=messages,
                    model=profile.model,
                    max_tokens=profile.max_tokens,
                    temperature=profile.temperature,
                    response_format={"type": "json_object"},
                    timeout=float(self._config.timeout_seconds),
                )
            except AITimeoutError:
                self._log(
                    request_id,
                    user_id,
                    feature,
                    profile.model,
                    AIOutcome.TIMEOUT,
                    started,
                    None,
                    None,
                    retry_count=attempt,
                )
                raise
            except AIProviderError:
                if attempt < self._max_attempts() - 1:
                    continue
                self._log(
                    request_id,
                    user_id,
                    feature,
                    profile.model,
                    AIOutcome.FAILED,
                    started,
                    None,
                    None,
                    retry_count=attempt,
                )
                raise AIProviderError("AI provider call failed", request_id) from None

            last_input_tokens, last_output_tokens = in_tok, out_tok
            validated = self._try_validate(text, schema)
            if validated is not None:
                outcome = AIOutcome.SUCCESS if attempt == 0 else AIOutcome.RETRY_SUCCESS
                self._log(
                    request_id,
                    user_id,
                    feature,
                    profile.model,
                    outcome,
                    started,
                    in_tok,
                    out_tok,
                    retry_count=attempt,
                )
                return validated
            # invalid schema/JSON — fall through to retry or terminal error

        # Exhausted attempts without a valid result.
        self._log(
            request_id,
            user_id,
            feature,
            profile.model,
            AIOutcome.INVALID_SCHEMA,
            started,
            last_input_tokens,
            last_output_tokens,
            retry_count=self._max_attempts() - 1,
        )
        raise AISchemaError("AI response failed schema validation after retry", request_id)

    def stream_structured(
        self,
        feature: AIFeature,
        system: str,
        user_blocks: list[str],
        schema: type[T],
        request_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream text deltas then yield a terminal validated-result event.

        Yields a ``StreamEvent(kind="delta", text=...)`` for each incremental
        chunk, then exactly one ``StreamEvent(kind="result", data=<schema>)``
        once the full text is accumulated and validated.

        Streaming does not retry (the transcript is already partially emitted).
        A validation failure raises ``AISchemaError``; a provider failure raises
        ``AIProviderError``; a timeout raises ``AITimeoutError``. One log row is
        written in all cases.

        Args:
            feature: Which AI feature is calling.
            system: System prompt (never logged).
            user_blocks: Delimited user content blocks.
            schema: Pydantic model to validate the accumulated text against.
            request_id: Correlation id.
            user_id: Optional owning user id.

        Yields:
            ``StreamEvent`` deltas followed by one result event.
        """
        profile = self._resolve_profile(feature)
        messages = self._build_messages(system, user_blocks)
        started = time.monotonic()
        chunks: list[str] = []

        try:
            for delta in self._provider.stream(
                messages=messages,
                model=profile.model,
                max_tokens=profile.max_tokens,
                temperature=profile.temperature,
                timeout=float(self._config.timeout_seconds),
            ):
                chunks.append(delta)
                yield StreamEvent(kind="delta", text=delta)
        except AITimeoutError:
            self._log(
                request_id,
                user_id,
                feature,
                profile.model,
                AIOutcome.TIMEOUT,
                started,
                None,
                None,
                retry_count=0,
            )
            raise
        except AIProviderError:
            self._log(
                request_id,
                user_id,
                feature,
                profile.model,
                AIOutcome.FAILED,
                started,
                None,
                None,
                retry_count=0,
            )
            raise AIProviderError("AI provider stream failed", request_id) from None

        validated = self._try_validate("".join(chunks), schema)
        if validated is None:
            self._log(
                request_id,
                user_id,
                feature,
                profile.model,
                AIOutcome.INVALID_SCHEMA,
                started,
                None,
                None,
                retry_count=0,
            )
            raise AISchemaError("AI streamed response failed schema validation", request_id)

        self._log(
            request_id,
            user_id,
            feature,
            profile.model,
            AIOutcome.SUCCESS,
            started,
            None,
            None,
            retry_count=0,
        )
        yield StreamEvent(kind="result", data=validated)

    # -- internals ---------------------------------------------------------

    def _max_attempts(self) -> int:
        """Total provider calls allowed = 1 initial + max_retries."""
        return 1 + max(0, self._config.max_retries)

    def _resolve_profile(self, feature: AIFeature) -> _TaskProfile:
        """Map an AIFeature to its (model, max_tokens, temperature) profile."""
        max_tokens = self._config.max_tokens
        if feature is AIFeature.RESUME_STRUCTURING:
            return _TaskProfile(self._config.default_model, max_tokens, 0.0)
        if feature is AIFeature.RESUME_REVIEW:
            return _TaskProfile(self._config.review_model, max_tokens, 0.2)
        if feature is AIFeature.PROFILE_OPTIMIZATION:
            return _TaskProfile(self._config.default_model, max_tokens, 0.2)
        # AIFeature.JOB_MATCHING
        return _TaskProfile(self._config.default_model, max_tokens, 0.0)

    @staticmethod
    def _build_messages(system: str, user_blocks: list[str]) -> list[dict[str, str]]:
        """Assemble the OpenAI-style message list from system + user blocks."""
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_blocks)},
        ]

    @staticmethod
    def _try_validate(text: str, schema: type[T]) -> T | None:
        """Parse ``text`` as JSON and validate against ``schema``.

        Returns the validated instance, or ``None`` if the text is not valid JSON
        or does not satisfy the schema. Raw text is never surfaced to the caller.
        """
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        try:
            return schema.model_validate(payload)
        except ValidationError:
            return None

    def _log(
        self,
        request_id: uuid.UUID,
        user_id: uuid.UUID | None,
        feature: AIFeature,
        model_id: str,
        outcome: AIOutcome,
        started_monotonic: float,
        input_tokens: int | None,
        output_tokens: int | None,
        retry_count: int,
    ) -> None:
        """Write exactly one metadata-only log row in its own committed session.

        The write is isolated from any caller transaction so a business rollback
        never erases observability, and a logging failure never breaks the AI call.
        NO prompt text, resume text, email, or filename is ever passed here.
        """
        latency_ms = int((time.monotonic() - started_monotonic) * 1000)
        try:
            session = self._db_session_factory()
            try:
                ai_log_repository.log_request(
                    session=session,
                    request_id=request_id,
                    user_id=user_id,
                    feature=feature,
                    model_id=model_id,
                    outcome=outcome,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    retry_count=retry_count,
                )
                session.commit()
            finally:
                session.close()
        except Exception:  # noqa: BLE001 — logging must never break the AI call
            logger.warning(
                "ai_request_log write failed",
                extra={"request_id": str(request_id), "outcome": str(outcome)},
            )
