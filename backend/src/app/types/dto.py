"""Request/response DTOs — the safe API boundary.

DTOs NEVER expose: password_hash, token_hash, storage_key, or raw embedding vectors.
Exclusion is by construction (fields simply do not exist on the DTO models).

No imports from app/config, app/db, app/repositories, app/services, or app/api.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.types.ai import ProfileOptimizationContent, ResumeReviewContent
from app.types.enums import (
    AIFeature,
    AIOutcome,
    JobSource,
    KnowledgeCategory,
    MimeType,
    ParseStatus,
    ReviewStatus,
    ThemePreference,
)
from app.types.structured import Citation, StructuredResume

# ---------------------------------------------------------------------------
# User DTOs
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Safe user record — no password_hash. Response DTO."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str
    theme_preference: ThemePreference
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Profile DTOs
# ---------------------------------------------------------------------------


class ProfileResponse(BaseModel):
    """Profile response DTO — no embedding. data-models.md §2.3."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None = None
    headline: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    completion_percentage: int = Field(default=0, ge=0, le=100)
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    """Partial profile update body."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=120)
    headline: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=2000)
    skills: list[str] | None = None
    education: list[dict[str, Any]] | None = None
    experience: list[dict[str, Any]] | None = None
    certifications: list[dict[str, Any]] | None = None
    projects: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Resume DTOs
# ---------------------------------------------------------------------------


class ResumeResponse(BaseModel):
    """Resume response DTO — no storage_key, no embedding. data-models.md §2.4."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    mime_type: MimeType
    size_bytes: int
    file_hash: str
    parse_status: ParseStatus
    structured_content: StructuredResume | None = None
    parse_error: str | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ResumeReview DTOs
# ---------------------------------------------------------------------------


class ResumeReviewResponse(BaseModel):
    """Resume review response DTO."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    resume_id: uuid.UUID
    user_id: uuid.UUID
    resume_file_hash: str
    status: ReviewStatus
    content: ResumeReviewContent | None = None
    sources: list[Citation] = Field(default_factory=list)
    model_id: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# ProfileOptimization DTOs
# ---------------------------------------------------------------------------


class ProfileOptimizationResponse(BaseModel):
    """Profile optimization response DTO."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    status: ReviewStatus
    content: ProfileOptimizationContent | None = None
    sources: list[Citation] = Field(default_factory=list)
    model_id: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Job DTOs
# ---------------------------------------------------------------------------


class JobResponse(BaseModel):
    """Job posting response DTO — no embedding vector."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    external_ref: str | None = None
    title: str
    company: str
    location: str
    employment_type: str | None = None
    description: str
    skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    source: JobSource
    created_at: datetime


# ---------------------------------------------------------------------------
# JobMatch DTOs
# ---------------------------------------------------------------------------


class JobMatchRunResponse(BaseModel):
    """Job match run response DTO."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user_id: uuid.UUID
    resume_id: uuid.UUID
    status: str
    model_id: str | None = None
    created_at: datetime


class JobMatchResponse(BaseModel):
    """Per-job match result DTO."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    run_id: uuid.UUID
    job_id: uuid.UUID
    fit_score: int = Field(ge=0, le=100)
    fit_explanation: str
    gaps: list[str] = Field(default_factory=list)
    rank: int = Field(ge=1)
    created_at: datetime


# ---------------------------------------------------------------------------
# KnowledgeChunk DTO (no embedding)
# ---------------------------------------------------------------------------


class KnowledgeChunkResponse(BaseModel):
    """Knowledge chunk response DTO — no embedding vector."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    source_file: str
    category: KnowledgeCategory
    chunk_index: int
    content: str
    content_hash: str
    created_at: datetime


# ---------------------------------------------------------------------------
# AIRequestLog DTO
# ---------------------------------------------------------------------------


class AIRequestLogResponse(BaseModel):
    """AI request log response DTO. Metadata only — never PII."""

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


# ---------------------------------------------------------------------------
# Auth DTOs
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """User registration request body."""

    model_config = ConfigDict(extra="forbid")

    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    """User login request body."""

    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class AuthSessionResponse(BaseModel):
    """Successful auth response (no token_hash, no refresh token in body)."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Standard error response envelope. api-contracts.md §0."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Wrapper for error detail."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
