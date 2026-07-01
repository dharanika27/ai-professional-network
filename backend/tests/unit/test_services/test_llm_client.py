"""Unit tests for app/services/ai/llm_client.py (mocked provider).

Covers AC-BEHAV-C01..C06, AC-SCHEMA-C01, and the no-raw-text-leak invariant.
The provider is always mocked; no groq SDK and no real DB are touched. Log
writes are captured by monkeypatching ai_log_repository.log_request and by a
fake session factory, so we can assert metadata-only, exactly-one-write behavior.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.config.llm_config import LLMConfig
from app.db.models import AIRequestLogModel
from app.repositories import ai_log_repository as ai_log_repo_module
from app.services.ai import llm_client as llm_client_module
from app.services.ai.llm_client import (
    AIProviderError,
    AISchemaError,
    AITimeoutError,
    LLMClient,
    StreamEvent,
)
from app.types.ai import ProfileOptimizationContent, ResumeReviewContent
from app.types.domain import AIRequestLog
from app.types.enums import AIFeature, AIOutcome
from app.types.structured import StructuredResume

# ---------------------------------------------------------------------------
# Fixtures / doubles
# ---------------------------------------------------------------------------

VALID_RESUME_JSON = (
    '{"contact": {"full_name": "A B", "email": "a@b.com"}, '
    '"skills": ["python"], "education": [], "experience": [], '
    '"certifications": [], "projects": []}'
)
VALID_REVIEW_JSON = '{"overall_summary": "ok", "strengths": [], "weaknesses": [], "ats_issues": [], "suggestions": []}'  # noqa: E501
VALID_PROFILE_JSON = '{"headline_suggestions": [], "summary_suggestion": null, "missing_skills": [], "section_suggestions": []}'  # noqa: E501


def _config() -> LLMConfig:
    return LLMConfig(
        provider="groq",
        review_model="review-model",
        default_model="default-model",
        max_tokens=4096,
        timeout_seconds=60,
        max_retries=1,
        ai_rate_limit_per_hour=10,
        groq_api_key=None,
    )


@dataclass
class _LogRow:
    kwargs: dict[str, object]


class _FakeProvider:
    """Provider double with scripted complete() and stream() behavior."""

    def __init__(
        self,
        complete_returns: list[tuple[str, int, int]] | None = None,
        complete_raises: list[Exception | None] | None = None,
        stream_deltas: list[str] | None = None,
        stream_raises: Exception | None = None,
    ) -> None:
        self._complete_returns = complete_returns or []
        self._complete_raises = complete_raises or []
        self._stream_deltas = stream_deltas or []
        self._stream_raises = stream_raises
        self.complete_calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        response_format: dict[str, str] | None,
        timeout: float,
    ) -> tuple[str, int, int]:
        idx = len(self.complete_calls)
        self.complete_calls.append(
            {
                "messages": messages,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
                "timeout": timeout,
            }
        )
        if idx < len(self._complete_raises) and self._complete_raises[idx] is not None:
            raise self._complete_raises[idx]  # type: ignore[misc]
        return self._complete_returns[idx]

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Iterator[str]:
        self.stream_calls.append({"model": model, "temperature": temperature})
        if self._stream_raises is not None:
            raise self._stream_raises
        yield from self._stream_deltas


@pytest.fixture()
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> list[_LogRow]:
    """Capture every log_request call's kwargs; also assert session lifecycle."""
    rows: list[_LogRow] = []

    def fake_log_request(**kwargs: object) -> object:
        rows.append(_LogRow(kwargs=kwargs))
        return object()

    monkeypatch.setattr(llm_client_module.ai_log_repository, "log_request", fake_log_request)
    return rows


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def session_factory() -> object:
    sessions: list[_FakeSession] = []

    def factory() -> _FakeSession:
        s = _FakeSession()
        sessions.append(s)
        return s

    factory.sessions = sessions  # type: ignore[attr-defined]
    return factory


def _make_client(provider: _FakeProvider, session_factory: object) -> LLMClient:
    return LLMClient(
        provider=provider,
        config=_config(),
        ai_log_repo=llm_client_module.ai_log_repository,
        db_session_factory=session_factory,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# AC-BEHAV-C01 — happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_validated_instance_no_retry(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[(VALID_RESUME_JSON, 10, 20)])
        client = _make_client(provider, session_factory)

        result = client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="sys",
            user_blocks=["resume text"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )

        assert isinstance(result, StructuredResume)
        assert result.contact.full_name == "A B"
        assert len(provider.complete_calls) == 1
        assert len(captured_logs) == 1
        row = captured_logs[0].kwargs
        assert row["outcome"] is AIOutcome.SUCCESS
        assert row["retry_count"] == 0
        assert row["input_tokens"] == 10
        assert row["output_tokens"] == 20
        # session committed and closed
        assert session_factory.sessions[0].committed is True  # type: ignore[attr-defined]
        assert session_factory.sessions[0].closed is True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# AC-BEHAV-C02 — single retry then safe error / retry then success
# ---------------------------------------------------------------------------


class TestRetryBehavior:
    def test_malformed_both_times_raises_schema_error(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[("not json", 5, 5), ("also not json", 5, 5)])
        client = _make_client(provider, session_factory)

        rid = uuid.uuid4()
        with pytest.raises(AISchemaError) as exc:
            client.complete_structured(
                feature=AIFeature.RESUME_STRUCTURING,
                system="sys",
                user_blocks=["x"],
                schema=StructuredResume,
                request_id=rid,
            )

        # exactly ONE retry -> provider called twice, at most 2 calls
        assert len(provider.complete_calls) == 2
        assert exc.value.request_id == rid
        # no raw provider text in the exception message
        assert "not json" not in str(exc.value)
        # single log row, invalid_schema
        assert len(captured_logs) == 1
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.INVALID_SCHEMA

    def test_valid_json_wrong_schema_retries_then_errors(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        """Well-formed JSON that violates the schema hits the ValidationError path."""
        # Valid JSON object, but missing required 'contact' -> schema validation fails.
        bad_shape = '{"skills": ["python"], "education": []}'
        provider = _FakeProvider(complete_returns=[(bad_shape, 1, 1), (bad_shape, 1, 1)])
        client = _make_client(provider, session_factory)
        with pytest.raises(AISchemaError):
            client.complete_structured(
                feature=AIFeature.RESUME_STRUCTURING,
                system="sys",
                user_blocks=["x"],
                schema=StructuredResume,
                request_id=uuid.uuid4(),
            )
        assert len(provider.complete_calls) == 2
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.INVALID_SCHEMA

    def test_retry_then_success_sets_retry_count_one(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[("bad", 1, 1), (VALID_RESUME_JSON, 7, 8)])
        client = _make_client(provider, session_factory)

        result = client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="sys",
            user_blocks=["x"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )

        assert isinstance(result, StructuredResume)
        assert len(provider.complete_calls) == 2
        assert len(captured_logs) == 1
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.RETRY_SUCCESS
        assert captured_logs[0].kwargs["retry_count"] == 1

    def test_provider_error_then_success(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        rid = uuid.uuid4()
        provider = _FakeProvider(
            complete_returns=[("", 0, 0), (VALID_RESUME_JSON, 1, 1)],
            complete_raises=[AIProviderError("boom", rid), None],
        )
        client = _make_client(provider, session_factory)

        result = client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="sys",
            user_blocks=["x"],
            schema=StructuredResume,
            request_id=rid,
        )
        assert isinstance(result, StructuredResume)
        assert len(provider.complete_calls) == 2

    def test_provider_error_both_times_raises_provider_error(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        rid = uuid.uuid4()
        provider = _FakeProvider(
            complete_returns=[("", 0, 0), ("", 0, 0)],
            complete_raises=[
                AIProviderError("raw-detail-a@b.com", rid),
                AIProviderError("raw-detail-a@b.com", rid),
            ],
        )
        client = _make_client(provider, session_factory)

        with pytest.raises(AIProviderError) as exc:
            client.complete_structured(
                feature=AIFeature.RESUME_STRUCTURING,
                system="sys",
                user_blocks=["x"],
                schema=StructuredResume,
                request_id=rid,
            )
        assert len(provider.complete_calls) == 2
        assert "a@b.com" not in str(exc.value)
        assert len(captured_logs) == 1
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.FAILED


# ---------------------------------------------------------------------------
# AC-BEHAV-C03 — metadata-only logging (no PII leak)
# ---------------------------------------------------------------------------


class TestMetadataOnlyLogging:
    def test_no_pii_in_any_log_field(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[(VALID_RESUME_JSON, 3, 4)])
        client = _make_client(provider, session_factory)

        client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="You are a parser. secret@email.com",
            user_blocks=["resume of secret@email.com from resume.pdf"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )

        assert len(captured_logs) == 1
        serialized = repr(captured_logs[0].kwargs)
        assert "secret@email.com" not in serialized
        assert "resume.pdf" not in serialized
        # allowed metadata keys only
        allowed = {
            "session",
            "request_id",
            "user_id",
            "feature",
            "model_id",
            "outcome",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "retry_count",
        }
        assert set(captured_logs[0].kwargs.keys()) <= allowed


# ---------------------------------------------------------------------------
# AC-BEHAV-C04 — timeout is non-retryable
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_timeout_not_retried_and_logged(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        rid = uuid.uuid4()
        provider = _FakeProvider(
            complete_returns=[("", 0, 0)],
            complete_raises=[AITimeoutError(rid)],
        )
        client = _make_client(provider, session_factory)

        with pytest.raises(AITimeoutError):
            client.complete_structured(
                feature=AIFeature.RESUME_REVIEW,
                system="sys",
                user_blocks=["x"],
                schema=ResumeReviewContent,
                request_id=rid,
            )
        # NOT retried
        assert len(provider.complete_calls) == 1
        assert len(captured_logs) == 1
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.TIMEOUT


# ---------------------------------------------------------------------------
# AC-BEHAV-C05 — config-driven model & temperature per feature
# ---------------------------------------------------------------------------


class TestConfigDriven:
    def test_structuring_uses_default_model_temp_zero(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[(VALID_RESUME_JSON, 1, 1)])
        client = _make_client(provider, session_factory)
        client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="s",
            user_blocks=["x"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )
        call = provider.complete_calls[0]
        assert call["model"] == "default-model"
        assert call["temperature"] == 0.0
        assert call["response_format"] == {"type": "json_object"}
        assert call["timeout"] == 60.0

    def test_review_uses_review_model_temp_point_two(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[(VALID_REVIEW_JSON, 1, 1)])
        client = _make_client(provider, session_factory)
        client.complete_structured(
            feature=AIFeature.RESUME_REVIEW,
            system="s",
            user_blocks=["x"],
            schema=ResumeReviewContent,
            request_id=uuid.uuid4(),
        )
        call = provider.complete_calls[0]
        assert call["model"] == "review-model"
        assert call["temperature"] == 0.2
        assert captured_logs[0].kwargs["model_id"] == "review-model"

    def test_profile_and_job_matching_use_default_model(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(
            complete_returns=[(VALID_PROFILE_JSON, 1, 1), (VALID_PROFILE_JSON, 1, 1)]
        )
        client = _make_client(provider, session_factory)
        client.complete_structured(
            feature=AIFeature.PROFILE_OPTIMIZATION,
            system="s",
            user_blocks=["x"],
            schema=ProfileOptimizationContent,
            request_id=uuid.uuid4(),
        )
        client.complete_structured(
            feature=AIFeature.JOB_MATCHING,
            system="s",
            user_blocks=["x"],
            schema=ProfileOptimizationContent,
            request_id=uuid.uuid4(),
        )
        assert provider.complete_calls[0]["model"] == "default-model"
        assert provider.complete_calls[0]["temperature"] == 0.2
        assert provider.complete_calls[1]["model"] == "default-model"
        assert provider.complete_calls[1]["temperature"] == 0.0


# ---------------------------------------------------------------------------
# AC-BEHAV-C06 — streaming
# ---------------------------------------------------------------------------


class TestStreaming:
    def test_stream_yields_deltas_then_result(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        # split the valid JSON across deltas
        mid = len(VALID_RESUME_JSON) // 2
        provider = _FakeProvider(stream_deltas=[VALID_RESUME_JSON[:mid], VALID_RESUME_JSON[mid:]])
        client = _make_client(provider, session_factory)

        events = list(
            client.stream_structured(
                feature=AIFeature.RESUME_STRUCTURING,
                system="s",
                user_blocks=["x"],
                schema=StructuredResume,
                request_id=uuid.uuid4(),
            )
        )
        deltas = [e for e in events if e.kind == "delta"]
        results = [e for e in events if e.kind == "result"]
        assert len(deltas) == 2
        assert len(results) == 1
        assert isinstance(results[0].data, StructuredResume)
        assert isinstance(results[-1], StreamEvent)
        assert len(captured_logs) == 1
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.SUCCESS

    def test_stream_invalid_json_raises_schema_error(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(stream_deltas=["not ", "json"])
        client = _make_client(provider, session_factory)
        rid = uuid.uuid4()
        gen = client.stream_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="s",
            user_blocks=["x"],
            schema=StructuredResume,
            request_id=rid,
        )
        with pytest.raises(AISchemaError):
            list(gen)
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.INVALID_SCHEMA

    def test_stream_provider_error(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        rid = uuid.uuid4()
        provider = _FakeProvider(stream_raises=AIProviderError("secret@email.com", rid))
        client = _make_client(provider, session_factory)
        gen = client.stream_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="s",
            user_blocks=["x"],
            schema=StructuredResume,
            request_id=rid,
        )
        with pytest.raises(AIProviderError) as exc:
            list(gen)
        assert "secret@email.com" not in str(exc.value)
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.FAILED

    def test_stream_timeout(self, captured_logs: list[_LogRow], session_factory: object) -> None:
        rid = uuid.uuid4()
        provider = _FakeProvider(stream_raises=AITimeoutError(rid))
        client = _make_client(provider, session_factory)
        with pytest.raises(AITimeoutError):
            list(
                client.stream_structured(
                    feature=AIFeature.RESUME_STRUCTURING,
                    system="s",
                    user_blocks=["x"],
                    schema=StructuredResume,
                    request_id=rid,
                )
            )
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.TIMEOUT


# ---------------------------------------------------------------------------
# AC-SCHEMA-C01 — generic over schema type
# ---------------------------------------------------------------------------


class TestGenericSchema:
    def test_works_with_review_content(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[(VALID_REVIEW_JSON, 1, 1)])
        client = _make_client(provider, session_factory)
        result = client.complete_structured(
            feature=AIFeature.RESUME_REVIEW,
            system="s",
            user_blocks=["x"],
            schema=ResumeReviewContent,
            request_id=uuid.uuid4(),
        )
        assert isinstance(result, ResumeReviewContent)

    def test_works_with_profile_content(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        provider = _FakeProvider(complete_returns=[(VALID_PROFILE_JSON, 1, 1)])
        client = _make_client(provider, session_factory)
        result = client.complete_structured(
            feature=AIFeature.PROFILE_OPTIMIZATION,
            system="s",
            user_blocks=["x"],
            schema=ProfileOptimizationContent,
            request_id=uuid.uuid4(),
        )
        assert isinstance(result, ProfileOptimizationContent)


# ---------------------------------------------------------------------------
# Logging robustness — a log write failure must not break the AI call
# ---------------------------------------------------------------------------


class TestLoggingRobustness:
    def test_log_failure_does_not_break_call(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: object
    ) -> None:
        def boom(**kwargs: object) -> object:
            raise RuntimeError("db down")

        monkeypatch.setattr(llm_client_module.ai_log_repository, "log_request", boom)
        provider = _FakeProvider(complete_returns=[(VALID_RESUME_JSON, 1, 1)])
        client = _make_client(provider, session_factory)
        result = client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="s",
            user_blocks=["x"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )
        assert isinstance(result, StructuredResume)


# ---------------------------------------------------------------------------
# ai_log_repository.log_request — metadata-only writer (fake session)
# ---------------------------------------------------------------------------


class _FlushingSession:
    """Fake session that mimics add + flush populating server-side defaults."""

    def __init__(self) -> None:
        self.added: list[AIRequestLogModel] = []

    def add(self, row: AIRequestLogModel) -> None:
        self.added.append(row)

    def flush(self) -> None:
        for row in self.added:
            if row.id is None:
                row.id = uuid.uuid4()
            if getattr(row, "created_at", None) is None:
                row.created_at = datetime.now(UTC)  # type: ignore[assignment]


class TestAiLogRepository:
    def test_log_request_writes_only_metadata_columns(self) -> None:
        """log_request persists one row with exactly the metadata fields and maps it."""
        session = _FlushingSession()
        rid = uuid.uuid4()
        uid = uuid.uuid4()

        result = ai_log_repo_module.log_request(
            session=session,  # type: ignore[arg-type]
            request_id=rid,
            user_id=uid,
            feature=AIFeature.RESUME_REVIEW,
            model_id="review-model",
            outcome=AIOutcome.RETRY_SUCCESS,
            latency_ms=123,
            input_tokens=10,
            output_tokens=20,
            retry_count=1,
        )

        assert isinstance(result, AIRequestLog)
        assert result.request_id == rid
        assert result.user_id == uid
        assert result.feature is AIFeature.RESUME_REVIEW
        assert result.outcome is AIOutcome.RETRY_SUCCESS
        assert result.model_id == "review-model"
        assert result.latency_ms == 123
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.retry_count == 1
        # the ORM row stores enum values as their string .value
        assert len(session.added) == 1
        row = session.added[0]
        assert row.feature == "resume_review"
        assert row.outcome == "retry_success"

    def test_log_request_allows_null_user_and_tokens(self) -> None:
        """user_id/token/latency may be None (anonymous or failed call)."""
        session = _FlushingSession()
        result = ai_log_repo_module.log_request(
            session=session,  # type: ignore[arg-type]
            request_id=uuid.uuid4(),
            user_id=None,
            feature=AIFeature.JOB_MATCHING,
            model_id="default-model",
            outcome=AIOutcome.TIMEOUT,
            latency_ms=None,
            input_tokens=None,
            output_tokens=None,
            retry_count=0,
        )
        assert result.user_id is None
        assert result.latency_ms is None
        assert result.input_tokens is None
        assert result.output_tokens is None


# ---------------------------------------------------------------------------
# Corrective retry — _build_messages with hint and _try_validate_with_hint
# ---------------------------------------------------------------------------


class TestCorrectiveRetry:
    """Tests for the corrective retry path introduced to fix the real-Groq failure.

    On a schema/parse failure the client must:
    1. Build messages WITH a corrective turn appended (so the model can fix structure).
    2. Succeed on the second attempt if the model returns valid JSON on retry.
    3. Never include PII / raw provider text in the corrective turn or exception.
    """

    def test_invalid_then_valid_succeeds_on_retry(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        """Provider returns invalid JSON on attempt 0, valid on attempt 1."""
        provider = _FakeProvider(complete_returns=[("not-json", 5, 5), (VALID_RESUME_JSON, 7, 8)])
        client = _make_client(provider, session_factory)

        result = client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="sys",
            user_blocks=["resume"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )

        assert isinstance(result, StructuredResume)
        assert len(provider.complete_calls) == 2
        # Retry attempt messages must contain a corrective user turn (4 messages).
        retry_msgs = provider.complete_calls[1]["messages"]
        assert len(retry_msgs) == 4  # system, user, assistant placeholder, corrective user
        assert retry_msgs[3]["role"] == "user"
        assert "not match the required JSON schema" in retry_msgs[3]["content"]
        # No raw provider text in the corrective message.
        assert "not-json" not in retry_msgs[3]["content"]
        # Log outcome is retry_success.
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.RETRY_SUCCESS

    def test_schema_mismatch_then_valid_succeeds_on_retry(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        """Provider returns structurally wrong JSON on attempt 0, valid on attempt 1."""
        bad_shape = '{"skills": ["x"], "education": []}'  # missing required 'contact'
        provider = _FakeProvider(complete_returns=[(bad_shape, 2, 2), (VALID_RESUME_JSON, 5, 6)])
        client = _make_client(provider, session_factory)

        result = client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="sys",
            user_blocks=["resume"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )

        assert isinstance(result, StructuredResume)
        assert len(provider.complete_calls) == 2
        retry_msgs = provider.complete_calls[1]["messages"]
        assert len(retry_msgs) == 4
        # The corrective hint mentions schema validation failure and the bad field loc.
        corrective_content = retry_msgs[3]["content"]
        assert "schema validation failed" in corrective_content
        assert captured_logs[0].kwargs["outcome"] is AIOutcome.RETRY_SUCCESS

    def test_first_attempt_messages_have_no_corrective_turn(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        """First attempt must send only 2 messages (system + user)."""
        provider = _FakeProvider(complete_returns=[(VALID_RESUME_JSON, 3, 4)])
        client = _make_client(provider, session_factory)

        client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="sys",
            user_blocks=["resume"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )

        first_msgs = provider.complete_calls[0]["messages"]
        assert len(first_msgs) == 2
        assert first_msgs[0]["role"] == "system"
        assert first_msgs[1]["role"] == "user"

    def test_corrective_hint_not_json_is_pii_free(self) -> None:
        """_try_validate_with_hint with bad JSON returns a PII-free hint."""
        from app.services.ai.llm_client import LLMClient

        _, hint = LLMClient._try_validate_with_hint("definitely not json {{{", StructuredResume)
        assert hint is not None
        assert "PII" not in hint
        assert "valid JSON" in hint
        # The raw text is never included.
        assert "definitely not json" not in hint

    def test_corrective_hint_schema_error_includes_field_locations(self) -> None:
        """_try_validate_with_hint with bad schema returns hint with field locs."""
        from app.services.ai.llm_client import LLMClient

        bad = '{"skills": ["x"]}'  # missing required 'contact'
        _, hint = LLMClient._try_validate_with_hint(bad, StructuredResume)
        assert hint is not None
        assert "contact" in hint  # field location surfaced

    def test_corrective_hint_success_returns_none_hint(self) -> None:
        """_try_validate_with_hint with valid JSON returns (instance, None)."""
        from app.services.ai.llm_client import LLMClient

        result, hint = LLMClient._try_validate_with_hint(VALID_RESUME_JSON, StructuredResume)
        assert isinstance(result, StructuredResume)
        assert hint is None

    def test_corrective_turn_no_pii_from_system_or_user_blocks(
        self, captured_logs: list[_LogRow], session_factory: object
    ) -> None:
        """The corrective user turn must not contain system or user-block content."""
        provider = _FakeProvider(complete_returns=[("bad", 1, 1), (VALID_RESUME_JSON, 2, 2)])
        client = _make_client(provider, session_factory)

        client.complete_structured(
            feature=AIFeature.RESUME_STRUCTURING,
            system="secret-sys-content",
            user_blocks=["secret-resume-text@pii.example.com"],
            schema=StructuredResume,
            request_id=uuid.uuid4(),
        )

        retry_msgs = provider.complete_calls[1]["messages"]
        corrective = retry_msgs[3]["content"]
        assert "secret-sys-content" not in corrective
        assert "secret-resume-text@pii.example.com" not in corrective


# ---------------------------------------------------------------------------
# Schema injection — RESUME_STRUCTURING_SYSTEM contains the JSON Schema
# ---------------------------------------------------------------------------


class TestSchemaInjection:
    """Tests that the resume structuring system prompt embeds the actual JSON Schema.

    AC-BEHAV-C10 injection-containment must remain intact. The schema content
    is injected into the system prompt (not user blocks), so the model receives
    the authoritative schema before any untrusted data.
    """

    def test_resume_structuring_system_contains_json_schema(self) -> None:
        """RESUME_STRUCTURING_SYSTEM must embed the StructuredResume JSON Schema."""
        from app.services.ai.prompts.resume_structuring import RESUME_STRUCTURING_SYSTEM
        from app.types.structured import StructuredResume

        # Top-level required field names must appear in the system prompt.
        schema = StructuredResume.model_json_schema()
        for field_name in schema.get("properties", {}):
            assert field_name in RESUME_STRUCTURING_SYSTEM, (
                f"System prompt missing schema field: {field_name}"
            )

    def test_resume_structuring_system_contains_schema_keyword(self) -> None:
        """System prompt must reference 'JSON Schema' so the model knows the format."""
        from app.services.ai.prompts.resume_structuring import RESUME_STRUCTURING_SYSTEM

        assert (
            "JSON Schema" in RESUME_STRUCTURING_SYSTEM
            or "json schema" in RESUME_STRUCTURING_SYSTEM.lower()
        )

    def test_schema_injected_in_system_not_user_block(self) -> None:
        """The structurer must pass the schema in the system prompt, not user blocks."""
        from app.services.parsing.structurer import structure_resume
        from app.types.structured import StructuredResume

        _valid_resume = StructuredResume(
            contact={"full_name": "Test", "email": "t@example.com"},  # type: ignore[arg-type]
        )

        class _Capturing:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def complete_structured(self, **kwargs: object) -> StructuredResume:
                self.calls.append(kwargs)
                return _valid_resume

        capturing = _Capturing()
        structure_resume("some resume", capturing, uuid.uuid4())  # type: ignore[arg-type]

        call = capturing.calls[0]
        system: str = call["system"]  # type: ignore[assignment]
        user_blocks: list[str] = call["user_blocks"]  # type: ignore[assignment]

        # Schema field names must appear in system, not user blocks.
        assert "contact" in system
        assert "skills" in system
        assert "education" in system
        # User block contains only the fenced resume text.
        for block in user_blocks:
            assert block.startswith("<resume_text>")
