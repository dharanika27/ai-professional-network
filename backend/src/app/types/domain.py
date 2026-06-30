"""Domain entity models — internal persistence-layer shapes.

These mirror data-models.md §2 exactly. They are NOT response DTOs;
they include all fields including ones never exposed (password_hash, token_hash,
storage_key, embedding). DTOs in dto.py are the safe API boundary.

No imports from app/config, app/db, app/repositories, app/services, or app/api.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.types.ai import ProfileOptimizationContent, ResumeReviewContent
from app.types.enums import (
    AIFeature,
    AIOutcome,
    JobMatchRunStatus,
    JobSource,
    KnowledgeCategory,
    MimeType,
    ParseStatus,
    ReviewStatus,
    ThemePreference,
)
from app.types.structured import Citation, StructuredResume


class User(BaseModel):
    """User auth identity. data-models.md §2.1."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str  # PII; stored lower-cased; unique
    password_hash: str  # Argon2id; never exposed in DTOs
    theme_preference: ThemePreference = ThemePreference.SYSTEM
    created_at: datetime
    updated_at: datetime


class RefreshToken(BaseModel):
    """JWT refresh-token lifecycle record. data-models.md §2.2."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str  # SHA-256 hex; never exposed in DTOs
    expires_at: datetime
    revoked: bool = False
    rotated_to: uuid.UUID | None = None
    created_at: datetime


class Profile(BaseModel):
    """Professional profile, one per user. data-models.md §2.3."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None = Field(default=None, max_length=120)  # PII
    headline: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)  # list[EducationItem]
    experience: list[dict[str, Any]] = Field(default_factory=list)  # list[ExperienceItem]
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    completion_percentage: int = Field(default=0, ge=0, le=100)
    created_at: datetime
    updated_at: datetime

    @field_validator("completion_percentage")
    @classmethod
    def validate_completion(cls, v: int) -> int:
        """Ensure completion_percentage is within 0-100."""
        if not 0 <= v <= 100:
            raise ValueError("completion_percentage must be between 0 and 100")
        return v


class Resume(BaseModel):
    """Resume file metadata + structured content. data-models.md §2.4."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str  # PII
    mime_type: MimeType
    size_bytes: int = Field(ge=1, le=5_242_880)
    file_hash: str  # SHA-256 hex
    storage_key: str  # never exposed in DTOs
    parse_status: ParseStatus = ParseStatus.PENDING
    structured_content: StructuredResume | None = None  # PII
    embedding: list[float] | None = None  # VEC384; never exposed in DTOs
    parse_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeReview(BaseModel):
    """AI resume critique result. data-models.md §2.5."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    resume_id: uuid.UUID
    user_id: uuid.UUID
    resume_file_hash: str
    status: ReviewStatus = ReviewStatus.PENDING
    content: ResumeReviewContent | None = None
    sources: list[Citation] = Field(default_factory=list)
    model_id: str | None = None
    created_at: datetime


class ProfileOptimization(BaseModel):
    """AI profile improvement result. data-models.md §2.6."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    status: ReviewStatus = ReviewStatus.PENDING
    content: ProfileOptimizationContent | None = None
    sources: list[Citation] = Field(default_factory=list)
    model_id: str | None = None
    created_at: datetime


class Job(BaseModel):
    """Seeded/loaded job posting. data-models.md §2.7."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    external_ref: str | None = None
    title: str = Field(max_length=200)
    company: str = Field(max_length=200)
    location: str
    employment_type: str | None = None
    description: str
    skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    embedding: list[float]  # VEC384; not exposed in DTOs
    source: JobSource = JobSource.SEED
    created_at: datetime


class JobMatchRun(BaseModel):
    """Job matching invocation record. data-models.md §2.8."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    resume_id: uuid.UUID
    status: JobMatchRunStatus = JobMatchRunStatus.PENDING
    model_id: str | None = None
    created_at: datetime


class JobMatch(BaseModel):
    """Per-job ranked result within a run. data-models.md §2.9."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    run_id: uuid.UUID
    job_id: uuid.UUID
    fit_score: int = Field(ge=0, le=100)
    fit_explanation: str
    gaps: list[str] = Field(default_factory=list)
    rank: int = Field(ge=1)
    created_at: datetime


class KnowledgeChunk(BaseModel):
    """RAG KB chunk record. data-models.md §2.10."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    source_file: str
    category: KnowledgeCategory
    chunk_index: int = Field(ge=0)
    content: str
    content_hash: str  # SHA-256
    embedding: list[float]  # VEC384; not exposed in DTOs
    created_at: datetime


class AIRequestLog(BaseModel):
    """AI call observability record. Metadata only — never PII. data-models.md §2.11."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    request_id: uuid.UUID
    user_id: uuid.UUID | None = None
    feature: AIFeature
    model_id: str
    outcome: AIOutcome
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    created_at: datetime
