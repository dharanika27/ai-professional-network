"""SQLAlchemy ORM table mappings.

Includes pgvector Vector(384) columns and HNSW vector indexes.
All enum fields stored as TEXT with CHECK constraints (portable, no native enum migration pain).
Matches data-models.md §2 exactly.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_THEMES = "('system','light','dark')"
_PARSE_STATUSES = "('pending','parsed','failed')"
_REVIEW_STATUSES = "('pending','completed','failed')"
_AI_FEATURES = "('resume_structuring','resume_review','profile_optimization','job_matching')"
_AI_OUTCOMES = "('success','retry_success','failed','timeout','invalid_schema','rate_limited')"
_KC_CATEGORIES = "('ats','resume','profile','interview','career')"
_JOB_SOURCES = "('seed','api')"
_MIME_TYPES = (
    "('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document')"
)


def _now() -> sa.sql.expression.FunctionElement:  # type: ignore[type-arg]
    return sa.func.now()


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


class UserModel(Base):
    """users table. data-models.md §2.1."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"theme_preference IN {_THEMES}", name="ck_users_theme_preference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    theme_preference: Mapped[str] = mapped_column(Text, nullable=False, server_default="system")
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    refresh_tokens: Mapped[list[RefreshTokenModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    profile: Mapped[ProfileModel | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    resumes: Mapped[list[ResumeModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    profile_optimizations: Mapped[list[ProfileOptimizationModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    job_match_runs: Mapped[list[JobMatchRunModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    ai_request_logs: Mapped[list[AIRequestLogModel]] = relationship(back_populates="user")


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------


class RefreshTokenModel(Base):
    """refresh_tokens table. data-models.md §2.2."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    rotated_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    user: Mapped[UserModel] = relationship(back_populates="refresh_tokens")


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------


class ProfileModel(Base):
    """profiles table. data-models.md §2.3."""

    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_profiles_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    education: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    experience: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    certifications: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="'[]'"
    )
    projects: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    completion_percentage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    user: Mapped[UserModel] = relationship(back_populates="profile")


# ---------------------------------------------------------------------------
# resumes
# ---------------------------------------------------------------------------


class ResumeModel(Base):
    """resumes table. data-models.md §2.4. Vector(384) embedding column."""

    __tablename__ = "resumes"
    __table_args__ = (
        CheckConstraint(f"mime_type IN {_MIME_TYPES}", name="ck_resumes_mime_type"),
        CheckConstraint("size_bytes >= 1 AND size_bytes <= 5242880", name="ck_resumes_size_bytes"),
        CheckConstraint(f"parse_status IN {_PARSE_STATUSES}", name="ck_resumes_parse_status"),
        UniqueConstraint("user_id", "file_hash", name="uq_resumes_user_file_hash"),
        Index("ix_resumes_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    parse_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    structured_content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    user: Mapped[UserModel] = relationship(back_populates="resumes")
    resume_reviews: Mapped[list[ResumeReviewModel]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    job_match_runs: Mapped[list[JobMatchRunModel]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# resume_reviews
# ---------------------------------------------------------------------------


class ResumeReviewModel(Base):
    """resume_reviews table. data-models.md §2.5."""

    __tablename__ = "resume_reviews"
    __table_args__ = (
        CheckConstraint(f"status IN {_REVIEW_STATUSES}", name="ck_resume_reviews_status"),
        Index("ix_resume_reviews_resume_id", "resume_id"),
        Index("ix_resume_reviews_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    resume: Mapped[ResumeModel] = relationship(back_populates="resume_reviews")


# ---------------------------------------------------------------------------
# profile_optimizations
# ---------------------------------------------------------------------------


class ProfileOptimizationModel(Base):
    """profile_optimizations table. data-models.md §2.6."""

    __tablename__ = "profile_optimizations"
    __table_args__ = (
        CheckConstraint(f"status IN {_REVIEW_STATUSES}", name="ck_profile_opts_status"),
        Index("ix_profile_opts_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    user: Mapped[UserModel] = relationship(back_populates="profile_optimizations")


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------


class JobModel(Base):
    """jobs table. data-models.md §2.7. Vector(384) embedding column."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"source IN {_JOB_SOURCES}", name="ck_jobs_source"),
        Index("ix_jobs_external_ref", "external_ref", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    seniority: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="seed")
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    job_matches: Mapped[list[JobMatchModel]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# job_match_runs
# ---------------------------------------------------------------------------


class JobMatchRunModel(Base):
    """job_match_runs table. data-models.md §2.8."""

    __tablename__ = "job_match_runs"
    __table_args__ = (
        CheckConstraint(f"status IN {_REVIEW_STATUSES}", name="ck_job_match_runs_status"),
        Index("ix_job_match_runs_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    model_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    user: Mapped[UserModel] = relationship(back_populates="job_match_runs")
    resume: Mapped[ResumeModel] = relationship(back_populates="job_match_runs")
    job_matches: Mapped[list[JobMatchModel]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# job_matches
# ---------------------------------------------------------------------------


class JobMatchModel(Base):
    """job_matches table. data-models.md §2.9."""

    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint("fit_score >= 0 AND fit_score <= 100", name="ck_job_matches_score"),
        UniqueConstraint("run_id", "job_id", name="uq_job_matches_run_job"),
        Index("ix_job_matches_run_rank", "run_id", "rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_match_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    fit_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fit_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    gaps: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="'[]'")
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    run: Mapped[JobMatchRunModel] = relationship(back_populates="job_matches")
    job: Mapped[JobModel] = relationship(back_populates="job_matches")


# ---------------------------------------------------------------------------
# knowledge_chunks
# ---------------------------------------------------------------------------


class KnowledgeChunkModel(Base):
    """knowledge_chunks table. data-models.md §2.10. Vector(384) embedding column."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        CheckConstraint(f"category IN {_KC_CATEGORIES}", name="ck_knowledge_chunks_category"),
        UniqueConstraint("content_hash", name="uq_knowledge_chunks_content_hash"),
        Index(
            "ix_knowledge_chunks_source_chunk",
            "source_file",
            "chunk_index",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )


# ---------------------------------------------------------------------------
# ai_request_logs
# ---------------------------------------------------------------------------


class AIRequestLogModel(Base):
    """ai_request_logs table. data-models.md §2.11. Metadata only — never PII."""

    __tablename__ = "ai_request_logs"
    __table_args__ = (
        CheckConstraint(f"feature IN {_AI_FEATURES}", name="ck_ai_logs_feature"),
        CheckConstraint(f"outcome IN {_AI_OUTCOMES}", name="ck_ai_logs_outcome"),
        Index("ix_ai_logs_request_id", "request_id"),
        Index("ix_ai_logs_user_created", "user_id", "created_at"),
        Index("ix_ai_logs_feature_outcome", "feature", "outcome"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[sa.DateTime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now()
    )

    user: Mapped[UserModel | None] = relationship(back_populates="ai_request_logs")
