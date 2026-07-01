"""Job repository — data-models.md §2.7, E7-S1.

Provides:
  - upsert_job          — insert-or-skip idempotent on external_ref
  - retrieve_top_jobs   — cosine similarity top-k search via pgvector
  - get_job_by_id       — lookup by primary key
  - get_job_count       — total job count

CRITICAL constraints (AC-IMPORT-B03, AC-IMPORT-B04):
  - MUST NOT import EmbeddingProvider, sentence_transformers, or any LLM client
  - MUST NOT import SeedJobLoader or JobLoader concrete class
  - Import JobRecord dataclass only from seeds/loaders
  - NEVER call session.commit(), session.rollback(), session.close()
  - NEVER import from app.services or app.api
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import JobModel
from app.types.domain import Job
from app.types.enums import JobSource

# Import only the JobRecord dataclass, not the loader Protocol or concrete class
from seeds.loaders.job_loader import JobRecord

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_job(row: JobModel) -> Job:
    """Map a JobModel ORM row to the Job domain object."""
    created_at: datetime
    if isinstance(row.created_at, datetime):
        created_at = row.created_at
    else:
        # Fallback: should not occur in practice
        created_at = datetime.utcnow()  # pragma: no cover

    return Job(
        id=row.id,
        external_ref=row.external_ref,
        title=row.title,
        company=row.company,
        location=row.location,
        employment_type=row.employment_type,
        description=row.description,
        skills=list(row.skills) if row.skills else [],
        seniority=row.seniority,
        embedding=list(row.embedding) if row.embedding is not None else [],
        source=JobSource(row.source),
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


def upsert_job(
    session: Session,
    record: JobRecord,
    embedding: list[float],
) -> uuid.UUID:
    """Insert or skip a job record (idempotent on external_ref).

    If a job with the same external_ref exists, returns its existing id (no duplicate).
    If external_ref is None, always inserts.
    Transaction boundary: caller owns commit/rollback.
    Returns the job id (new or existing).
    """
    # Check for existing record if external_ref is provided
    if record.external_ref is not None:
        stmt = sa.select(JobModel).where(JobModel.external_ref == record.external_ref)
        existing = session.scalars(stmt).first()
        if existing is not None:
            return existing.id

    # Insert new job
    row = JobModel(
        external_ref=record.external_ref,
        title=record.title,
        company=record.company,
        location=record.location,
        employment_type=record.employment_type,
        description=record.description,
        skills=record.skills,
        seniority=record.seniority,
        embedding=embedding,
        source=record.source,
    )
    session.add(row)
    session.flush()
    return row.id


def retrieve_top_jobs(
    session: Session,
    query_embedding: list[float],
    k: int = 10,
) -> list[Job]:
    """Return top-k Jobs ordered by cosine similarity to query_embedding.

    Uses pgvector: ORDER BY embedding <=> :qv LIMIT :k
    Never calls EmbeddingProvider — query embedding is passed in as argument.
    Returns domain Job objects.
    """
    rows = (
        session.execute(
            sa.select(JobModel).order_by(JobModel.embedding.op("<=>")(query_embedding)).limit(k)
        )
        .scalars()
        .all()
    )
    return [_to_job(row) for row in rows]


def get_job_by_id(session: Session, job_id: uuid.UUID) -> Job | None:
    """Return the full Job record or None if not found."""
    stmt = sa.select(JobModel).where(JobModel.id == job_id)
    row = session.scalars(stmt).first()
    return _to_job(row) if row is not None else None


def get_job_count(session: Session) -> int:
    """Return total number of jobs."""
    result = session.execute(sa.select(sa.func.count()).select_from(JobModel))
    count: int = result.scalar_one()
    return count
