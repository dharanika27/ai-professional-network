"""Real-Groq integration tests (gated on GROQ_API_KEY).

These exercise the concrete GroqProvider against the live Groq API. They are
skipped unless GROQ_API_KEY is set in the environment and require the ``groq``
SDK to be installed. Run explicitly with:

    GROQ_API_KEY=... uv run pytest -m groq_integration tests/integration/test_groq_integration.py
"""

from __future__ import annotations

import os
import uuid

import pytest

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

_MINIMAL_RESUME = (
    "Jane Doe\njane@example.com | +1-555-0100 | Berlin\n\n"
    "Skills: Python, SQL, Docker\n\n"
    "Experience:\nAcme Corp — Senior Engineer (2021-01 to present). "
    "Built data pipelines.\n\n"
    "Education:\nBSc Computer Science, TU Berlin, 2016-2020.\n\n"
    "Certifications: AWS Solutions Architect (2022-03)\n\n"
    "Projects: OpenMetrics — telemetry library (Python)."
)

_SYSTEM = (
    "You extract a resume into strict JSON with exactly these keys: "
    "contact (object with full_name,email,phone,location,links), skills (array of strings), "
    "education (array), experience (array), certifications (array), projects (array). "
    "Return ONLY the JSON object."
)


@pytest.mark.groq_integration
@pytest.mark.skipif(not GROQ_API_KEY, reason="GROQ_API_KEY not set")
def test_groq_structured_resume_output() -> None:
    """Real Groq call: JSON output validates as StructuredResume via LLMClient."""
    from app.config.llm_config import LLMConfig
    from app.repositories import ai_log_repository
    from app.services.ai.groq_provider import GroqProvider
    from app.services.ai.llm_client import LLMClient
    from app.types.enums import AIFeature
    from app.types.structured import StructuredResume

    config = LLMConfig(
        provider="groq",
        review_model="llama-3.3-70b-versatile",
        default_model="llama-3.1-8b-instant",
        max_tokens=2048,
        timeout_seconds=60,
        max_retries=1,
        ai_rate_limit_per_hour=10,
        groq_api_key=GROQ_API_KEY,
    )

    class _NullSession:
        def commit(self) -> None: ...
        def close(self) -> None: ...

    provider = GroqProvider(api_key=GROQ_API_KEY)
    client = LLMClient(
        provider=provider,
        config=config,
        ai_log_repo=ai_log_repository,
        db_session_factory=_NullSession,  # type: ignore[arg-type]
    )

    result = client.complete_structured(
        feature=AIFeature.RESUME_STRUCTURING,
        system=_SYSTEM,
        user_blocks=[_MINIMAL_RESUME],
        schema=StructuredResume,
        request_id=uuid.uuid4(),
    )

    assert isinstance(result, StructuredResume)
    assert result.contact is not None
    # The six-key schema is present and typed; content specifics are model-dependent.
    assert isinstance(result.skills, list)
    assert isinstance(result.education, list)
    assert isinstance(result.experience, list)
    assert isinstance(result.certifications, list)
    assert isinstance(result.projects, list)


@pytest.mark.groq_integration
@pytest.mark.skipif(not GROQ_API_KEY, reason="GROQ_API_KEY not set")
def test_groq_provider_raw_complete_returns_tokens() -> None:
    """Real Groq call at the provider level returns text and token counts."""
    from app.services.ai.groq_provider import GroqProvider

    provider = GroqProvider(api_key=GROQ_API_KEY)
    text, in_tok, out_tok = provider.complete(
        messages=[{"role": "user", "content": 'Reply with JSON {"ok": true}'}],
        model="llama-3.1-8b-instant",
        max_tokens=64,
        temperature=0.0,
        response_format={"type": "json_object"},
        timeout=60.0,
    )
    assert isinstance(text, str) and text.strip()
    assert in_tok > 0
    assert out_tok > 0
