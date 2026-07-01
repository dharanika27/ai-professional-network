"""AI request log repository — metadata-only observability writer.

Writes exactly one ``ai_request_logs`` row per AI call. The row carries ONLY
call metadata:

    {request_id, user_id, feature, model_id, outcome, latency_ms,
     input_tokens, output_tokens, retry_count, created_at}

It NEVER stores prompt text, resume text, PII, email, or filename — those
values are never passed to this module, and there is no column for them.

Transaction ownership: the caller owns commit/rollback/close. This module never
commits, rolls back, or closes the session (matches the repository-layer rule).
No imports from app.services or app.api.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import AIRequestLogModel
from app.types.domain import AIRequestLog
from app.types.enums import AIFeature, AIOutcome


def log_request(
    session: Session,
    request_id: uuid.UUID,
    user_id: uuid.UUID | None,
    feature: AIFeature,
    model_id: str,
    outcome: AIOutcome,
    latency_ms: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    retry_count: int,
) -> AIRequestLog:
    """Insert one metadata-only AI request log row and return the domain model.

    ``session.flush()`` populates the generated UUID/created_at without requiring
    the caller to commit. The caller owns the transaction.

    Args:
        session: An injected SQLAlchemy Session.
        request_id: Correlation id for the AI call.
        user_id: Owning user id, or None for anonymous/system calls.
        feature: Which AI feature produced the call.
        model_id: Provider model identifier used.
        outcome: Terminal outcome of the call.
        latency_ms: Wall-clock latency in milliseconds, or None.
        input_tokens: Provider-reported prompt tokens, or None.
        output_tokens: Provider-reported completion tokens, or None.
        retry_count: Number of retries performed (0 on first-attempt success).

    Returns:
        The persisted :class:`AIRequestLog` domain model with id/created_at set.
    """
    row = AIRequestLogModel(
        request_id=request_id,
        user_id=user_id,
        feature=feature.value,
        model_id=model_id,
        outcome=outcome.value,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        retry_count=retry_count,
    )
    session.add(row)
    session.flush()
    return _to_domain(row)


def _to_domain(row: AIRequestLogModel) -> AIRequestLog:
    """Map an AIRequestLogModel ORM row to the AIRequestLog domain model."""
    return AIRequestLog(
        id=row.id,
        request_id=row.request_id,
        user_id=row.user_id,
        feature=AIFeature(row.feature),
        model_id=row.model_id,
        outcome=AIOutcome(row.outcome),
        latency_ms=row.latency_ms,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        retry_count=row.retry_count,
        created_at=row.created_at,
    )
