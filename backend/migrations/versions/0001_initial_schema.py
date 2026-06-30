"""Initial schema: pgvector extension + all tables with vector(384) columns.

Revision ID: 0001_initial_schema
Revises: (none — initial revision)
Create Date: 2026-06-30 00:00:00.000000

Creates:
  - pgvector extension
  - All 11 entity tables per data-models.md §2
  - Vector(384) columns on resumes, jobs, knowledge_chunks
  - HNSW (cosine) indexes on all three vector columns
  - CHECK constraints for all enum columns
  - All unique indexes and FK relationships
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Use sa.text() for server_default so SQLAlchemy doesn't add extra quoting
_EMPTY_JSON_ARRAY = sa.text("'[]'")
_NOW = sa.text("now()")


def upgrade() -> None:
    """Apply the initial schema."""
    # ------------------------------------------------------------------
    # 1. Enable pgvector extension (idempotent)
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # 2. users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column(
            "theme_preference",
            sa.Text,
            nullable=False,
            server_default="system",
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "theme_preference IN ('system','light','dark')",
            name="ck_users_theme_preference",
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ------------------------------------------------------------------
    # 3. refresh_tokens
    # ------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text, nullable=False),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "revoked",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "rotated_to",
            UUID(as_uuid=True),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    # ------------------------------------------------------------------
    # 4. profiles
    # ------------------------------------------------------------------
    op.create_table(
        "profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.Text, nullable=True),
        sa.Column("headline", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("skills", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("education", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("experience", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("certifications", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("projects", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column(
            "completion_percentage",
            sa.SmallInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.UniqueConstraint("user_id", name="uq_profiles_user_id"),
    )

    # ------------------------------------------------------------------
    # 5. resumes (vector(384) embedding)
    # ------------------------------------------------------------------
    op.create_table(
        "resumes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("mime_type", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("file_hash", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column(
            "parse_status",
            sa.Text,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("structured_content", JSONB, nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("parse_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "mime_type IN ('application/pdf',"
            "'application/vnd.openxmlformats-officedocument.wordprocessingml.document')",
            name="ck_resumes_mime_type",
        ),
        sa.CheckConstraint(
            "size_bytes >= 1 AND size_bytes <= 5242880",
            name="ck_resumes_size_bytes",
        ),
        sa.CheckConstraint(
            "parse_status IN ('pending','parsed','failed')",
            name="ck_resumes_parse_status",
        ),
        sa.UniqueConstraint("user_id", "file_hash", name="uq_resumes_user_file_hash"),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])
    # HNSW cosine index on embedding
    op.execute(
        "CREATE INDEX resumes_embedding_hnsw ON resumes USING hnsw (embedding vector_cosine_ops)"
    )

    # ------------------------------------------------------------------
    # 6. resume_reviews
    # ------------------------------------------------------------------
    op.create_table(
        "resume_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "resume_id",
            UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resume_file_hash", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("content", JSONB, nullable=True),
        sa.Column("sources", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("model_id", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed','failed')",
            name="ck_resume_reviews_status",
        ),
    )
    op.create_index("ix_resume_reviews_resume_id", "resume_reviews", ["resume_id"])
    op.create_index("ix_resume_reviews_user_id", "resume_reviews", ["user_id"])

    # ------------------------------------------------------------------
    # 7. profile_optimizations
    # ------------------------------------------------------------------
    op.create_table(
        "profile_optimizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("content", JSONB, nullable=True),
        sa.Column("sources", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("model_id", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed','failed')",
            name="ck_profile_opts_status",
        ),
    )
    op.create_index(
        "ix_profile_opts_user_created",
        "profile_optimizations",
        ["user_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # 8. jobs (vector(384) embedding)
    # ------------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_ref", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("company", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=False),
        sa.Column("employment_type", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("skills", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("seniority", sa.Text, nullable=True),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("source", sa.Text, nullable=False, server_default="seed"),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint("source IN ('seed','api')", name="ck_jobs_source"),
    )
    op.create_index("ix_jobs_external_ref", "jobs", ["external_ref"], unique=True)
    # HNSW cosine index on embedding
    op.execute("CREATE INDEX jobs_embedding_hnsw ON jobs USING hnsw (embedding vector_cosine_ops)")

    # ------------------------------------------------------------------
    # 9. job_match_runs
    # ------------------------------------------------------------------
    op.create_table(
        "job_match_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resume_id",
            UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("model_id", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed','failed')",
            name="ck_job_match_runs_status",
        ),
    )
    op.create_index(
        "ix_job_match_runs_user_created",
        "job_match_runs",
        ["user_id", "created_at"],
    )

    # ------------------------------------------------------------------
    # 10. job_matches
    # ------------------------------------------------------------------
    op.create_table(
        "job_matches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_match_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fit_score", sa.SmallInteger, nullable=False),
        sa.Column("fit_explanation", sa.Text, nullable=False),
        sa.Column("gaps", JSONB, nullable=False, server_default=_EMPTY_JSON_ARRAY),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "fit_score >= 0 AND fit_score <= 100",
            name="ck_job_matches_score",
        ),
        sa.UniqueConstraint("run_id", "job_id", name="uq_job_matches_run_job"),
    )
    op.create_index("ix_job_matches_run_rank", "job_matches", ["run_id", "rank"])

    # ------------------------------------------------------------------
    # 11. knowledge_chunks (vector(384) embedding)
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "category IN ('ats','resume','profile','interview','career')",
            name="ck_knowledge_chunks_category",
        ),
        sa.UniqueConstraint("content_hash", name="uq_knowledge_chunks_content_hash"),
    )
    op.create_index(
        "ix_knowledge_chunks_source_chunk",
        "knowledge_chunks",
        ["source_file", "chunk_index"],
    )
    # HNSW cosine index on embedding
    op.execute(
        "CREATE INDEX knowledge_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ------------------------------------------------------------------
    # 12. ai_request_logs
    # ------------------------------------------------------------------
    op.create_table(
        "ai_request_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("feature", sa.Text, nullable=False),
        sa.Column("model_id", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column(
            "retry_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.CheckConstraint(
            "feature IN ('resume_structuring','resume_review',"
            "'profile_optimization','job_matching')",
            name="ck_ai_logs_feature",
        ),
        sa.CheckConstraint(
            "outcome IN ('success','retry_success','failed',"
            "'timeout','invalid_schema','rate_limited')",
            name="ck_ai_logs_outcome",
        ),
    )
    op.create_index("ix_ai_logs_request_id", "ai_request_logs", ["request_id"])
    op.create_index(
        "ix_ai_logs_user_created",
        "ai_request_logs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_logs_feature_outcome",
        "ai_request_logs",
        ["feature", "outcome"],
    )


def downgrade() -> None:
    """Reverse the initial schema migration."""
    # Drop in reverse dependency order
    op.drop_table("ai_request_logs")
    op.drop_table("knowledge_chunks")
    op.drop_table("job_matches")
    op.drop_table("job_match_runs")
    op.drop_table("jobs")
    op.drop_table("profile_optimizations")
    op.drop_table("resume_reviews")
    op.drop_table("resumes")
    op.drop_table("profiles")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    # Note: intentionally do NOT drop the vector extension on downgrade
    # as other migrations / applications may depend on it.
