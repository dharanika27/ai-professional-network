"""Turn raw resume text into a validated ``StructuredResume`` via the LLM client.

The untrusted resume text is delimited and injection-contained by the prompt
builder; the system contract is authored separately and passed as the system
message so the two can never be merged. Typed AI errors from the client
(``AISchemaError`` / ``AIProviderError`` / ``AITimeoutError``) propagate
unchanged — they are already safe and PII-free. No fastapi import.
"""

from __future__ import annotations

import uuid

from app.services.ai.llm_client import LLMClient
from app.services.ai.prompts.resume_structuring import (
    RESUME_STRUCTURING_SYSTEM,
    build_resume_structuring_prompt,
)
from app.types.enums import AIFeature
from app.types.structured import StructuredResume


def structure_resume(
    raw_text: str,
    llm_client: LLMClient,
    request_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> StructuredResume:
    """Send ``raw_text`` to the LLM and return a validated ``StructuredResume``.

    The system contract is passed as ``system`` and the untrusted resume text is
    passed as a single delimited user block, so nothing in the resume text can
    override the instructions.

    Args:
        raw_text: Extracted, UNTRUSTED resume text.
        llm_client: The provider-agnostic LLM orchestration client.
        request_id: Correlation id for logging.
        user_id: Optional owning user id.

    Returns:
        A validated ``StructuredResume``.

    Raises:
        AISchemaError: Output failed schema validation after the client's retry.
        AIProviderError: The provider failed.
        AITimeoutError: The provider timed out.
    """
    user_block = build_resume_structuring_prompt(raw_text)
    return llm_client.complete_structured(
        feature=AIFeature.RESUME_STRUCTURING,
        system=RESUME_STRUCTURING_SYSTEM,
        user_blocks=[user_block],
        schema=StructuredResume,
        request_id=request_id,
        user_id=user_id,
    )
