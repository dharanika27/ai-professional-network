"""Tests for app/services/ai/llm_provider.py and groq_provider.py.

Verifies the LLMProvider Protocol accepts conforming stubs and the concrete
GroqProvider, and that GroqProvider isolates the groq SDK and normalizes errors
without leaking raw payloads. The real groq SDK is mocked — these are unit tests.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from app.services.ai.groq_provider import GroqProvider
from app.services.ai.llm_client import AIProviderError, AITimeoutError
from app.services.ai.llm_provider import LLMProvider


class TestProtocolConformance:
    def test_stub_satisfies_protocol(self) -> None:
        """A minimal stub implementing both methods satisfies LLMProvider."""

        class StubProvider:
            def complete(
                self,
                messages: list[dict[str, str]],
                model: str,
                max_tokens: int,
                temperature: float,
                response_format: dict[str, str] | None,
                timeout: float,
            ) -> tuple[str, int, int]:
                return ("{}", 1, 2)

            def stream(
                self,
                messages: list[dict[str, str]],
                model: str,
                max_tokens: int,
                temperature: float,
                timeout: float,
            ) -> Iterator[str]:
                yield "x"

        assert isinstance(StubProvider(), LLMProvider)

    def test_groq_provider_satisfies_protocol(self) -> None:
        """GroqProvider satisfies the LLMProvider protocol (no SDK needed)."""
        assert isinstance(GroqProvider(api_key="k"), LLMProvider)

    def test_incomplete_stub_fails_protocol(self) -> None:
        """A class missing stream() does not satisfy the protocol."""

        class Partial:
            def complete(self, *args: object, **kwargs: object) -> tuple[str, int, int]:
                return ("", 0, 0)

        assert not isinstance(Partial(), LLMProvider)


def _install_fake_groq(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    """Install a fake ``groq`` module exposing ``Groq`` -> ``client``."""
    fake = types.ModuleType("groq")
    fake.Groq = MagicMock(return_value=client)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "groq", fake)


def _completion(text: str, prompt: int, completion: int) -> MagicMock:
    result = MagicMock()
    result.choices = [MagicMock()]
    result.choices[0].message.content = text
    result.usage.prompt_tokens = prompt
    result.usage.completion_tokens = completion
    return result


class TestGroqProviderComplete:
    def test_complete_returns_text_and_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """complete() returns (text, input_tokens, output_tokens) from the SDK."""
        client = MagicMock()
        client.chat.completions.create.return_value = _completion('{"a":1}', 11, 22)
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        text, in_tok, out_tok = provider.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="llama-3.1-8b-instant",
            max_tokens=100,
            temperature=0.0,
            response_format={"type": "json_object"},
            timeout=60.0,
        )
        assert text == '{"a":1}'
        assert in_tok == 11
        assert out_tok == 22
        # response_format was forwarded
        _, kwargs = client.chat.completions.create.call_args
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_complete_handles_none_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None message content coerces to empty string, not a crash."""
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(None, 1, 0)  # type: ignore[arg-type]
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        text, _, _ = provider.complete(
            messages=[],
            model="m",
            max_tokens=1,
            temperature=0.0,
            response_format=None,
            timeout=1.0,
        )
        assert text == ""

    def test_complete_wraps_generic_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A generic SDK error becomes AIProviderError with no raw payload leak."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("secret@email.com boom")
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        with pytest.raises(AIProviderError) as exc:
            provider.complete(
                messages=[],
                model="m",
                max_tokens=1,
                temperature=0.0,
                response_format=None,
                timeout=1.0,
            )
        assert "secret@email.com" not in str(exc.value)

    def test_complete_wraps_timeout_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A timeout-shaped SDK error becomes AITimeoutError."""
        client = MagicMock()

        class APITimeoutError(Exception):
            pass

        client.chat.completions.create.side_effect = APITimeoutError("timed out")
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        with pytest.raises(AITimeoutError):
            provider.complete(
                messages=[],
                model="m",
                max_tokens=1,
                temperature=0.0,
                response_format=None,
                timeout=1.0,
            )

    def test_builtin_timeouterror_maps_to_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Python's built-in TimeoutError also maps to AITimeoutError."""
        client = MagicMock()
        client.chat.completions.create.side_effect = TimeoutError()
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        with pytest.raises(AITimeoutError):
            provider.complete(
                messages=[],
                model="m",
                max_tokens=1,
                temperature=0.0,
                response_format=None,
                timeout=1.0,
            )


class TestGroqProviderStream:
    def test_stream_yields_deltas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """stream() yields non-empty content deltas in order."""

        def make_chunk(content: str | None) -> MagicMock:
            ch = MagicMock()
            ch.choices = [MagicMock()]
            ch.choices[0].delta.content = content
            return ch

        client = MagicMock()
        client.chat.completions.create.return_value = iter(
            [make_chunk("Hel"), make_chunk(None), make_chunk("lo")]
        )
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        deltas = list(
            provider.stream(messages=[], model="m", max_tokens=10, temperature=0.0, timeout=1.0)
        )
        assert deltas == ["Hel", "lo"]
        _, kwargs = client.chat.completions.create.call_args
        assert kwargs["stream"] is True

    def test_stream_wraps_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stream error normalizes to AIProviderError."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("boom")
        _install_fake_groq(monkeypatch, client)

        provider = GroqProvider(api_key="k")
        with pytest.raises(AIProviderError):
            list(
                provider.stream(messages=[], model="m", max_tokens=10, temperature=0.0, timeout=1.0)
            )

    def test_client_built_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The SDK client is constructed lazily and reused across calls."""
        client = MagicMock()
        client.chat.completions.create.return_value = _completion("{}", 0, 0)
        fake = types.ModuleType("groq")
        groq_ctor = MagicMock(return_value=client)
        fake.Groq = groq_ctor  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "groq", fake)

        provider = GroqProvider(api_key="k")
        provider.complete(
            messages=[],
            model="m",
            max_tokens=1,
            temperature=0.0,
            response_format=None,
            timeout=1.0,
        )
        provider.complete(
            messages=[],
            model="m",
            max_tokens=1,
            temperature=0.0,
            response_format=None,
            timeout=1.0,
        )
        assert groq_ctor.call_count == 1
        groq_ctor.assert_called_once_with(api_key="k")
