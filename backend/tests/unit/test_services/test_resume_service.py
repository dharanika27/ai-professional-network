"""Unit tests for app/services/resume_service.py.

``process_resume`` orchestrates extract → structure. The LLM client is faked and
we assert it is NEVER called when extraction fails, that typed extraction errors
propagate unchanged, and that AI errors surface as the client's safe typed errors.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.ai.llm_client import AISchemaError
from app.services.parsing.extractor import ExtractionError, InvalidFileTypeError
from app.services.resume_service import process_resume
from app.types.enums import MIME_PDF
from app.types.structured import StructuredResume
from tests.unit.test_services.test_extractor import make_test_pdf

VALID_RESUME = StructuredResume(
    contact={"full_name": "John Smith", "email": "john@example.com"},  # type: ignore[arg-type]
    skills=["Python"],
)


class _CapturingLLMClient:
    def __init__(self, result: Any = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    def complete_structured(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._result


def test_happy_path_returns_structured_resume() -> None:
    client = _CapturingLLMClient(result=VALID_RESUME)
    out = process_resume(make_test_pdf(), MIME_PDF, "resume.pdf", client, uuid.uuid4())  # type: ignore[arg-type]
    assert out is VALID_RESUME
    assert len(client.calls) == 1


def test_invalid_file_type_propagates_and_skips_llm() -> None:
    client = _CapturingLLMClient(result=VALID_RESUME)
    with pytest.raises(InvalidFileTypeError):
        process_resume(make_test_pdf(), "text/plain", "resume.pdf", client, uuid.uuid4())  # type: ignore[arg-type]
    assert client.calls == []


def test_corrupt_file_propagates_extraction_error_and_skips_llm() -> None:
    client = _CapturingLLMClient(result=VALID_RESUME)
    with pytest.raises(ExtractionError):
        process_resume(b"garbage", MIME_PDF, "resume.pdf", client, uuid.uuid4())  # type: ignore[arg-type]
    assert client.calls == []


def test_llm_failure_propagates() -> None:
    rid = uuid.uuid4()
    client = _CapturingLLMClient(raises=AISchemaError("bad", rid))
    with pytest.raises(AISchemaError):
        process_resume(make_test_pdf(), MIME_PDF, "resume.pdf", client, rid)  # type: ignore[arg-type]
    assert len(client.calls) == 1
