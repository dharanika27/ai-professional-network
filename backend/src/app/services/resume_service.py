"""Resume processing orchestration: extract → structure.

Ties the local extractor to the LLM-backed structurer. Extraction failures
surface as their own typed errors (``InvalidFileTypeError`` / ``ExtractionError``)
and the LLM is never called when extraction fails. AI failures propagate as the
client's safe typed errors. Nothing is persisted here — storage is the caller's
responsibility. No fastapi import.
"""

from __future__ import annotations

import uuid

from app.services.ai.llm_client import LLMClient
from app.services.parsing.extractor import extract_text
from app.services.parsing.structurer import structure_resume
from app.types.structured import StructuredResume


class ResumeParseError(Exception):
    """Safe, user-facing error when resume processing fails.

    The message never contains resume content, filenames, or PII.
    """


def process_resume(
    file_bytes: bytes,
    mime_type: str,
    filename: str,
    llm_client: LLMClient,
    request_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> StructuredResume:
    """Orchestrate extract → structure and return a validated ``StructuredResume``.

    Args:
        file_bytes: Raw uploaded file content.
        mime_type: Declared MIME type.
        filename: Original filename (used for extension validation).
        llm_client: The provider-agnostic LLM orchestration client.
        request_id: Correlation id for logging.
        user_id: Optional owning user id.

    Returns:
        A validated ``StructuredResume``.

    Raises:
        InvalidFileTypeError: Disallowed/mismatched MIME or extension, or oversize.
        ExtractionError: The file could not be extracted (corrupt/empty/protected).
        AISchemaError: The LLM output failed schema validation after retry.
        AIProviderError: The provider failed.
        AITimeoutError: The provider timed out.
    """
    raw_text = extract_text(file_bytes, mime_type, filename)
    return structure_resume(raw_text, llm_client, request_id, user_id)
