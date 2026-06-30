"""Tests for app/db/models.py — F012, AC-SCHEMA-05.

Verifies that ORM models declare vector(384) columns on resumes, jobs,
and knowledge_chunks, and that CHECK constraints exist for enums.

These are static structural tests — they do not require a live DB.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.base import Base
from app.db.models import (
    AIRequestLogModel,
    JobMatchModel,
    JobMatchRunModel,
    JobModel,
    KnowledgeChunkModel,
    ProfileModel,
    ProfileOptimizationModel,
    RefreshTokenModel,
    ResumeModel,
    ResumeReviewModel,
    UserModel,
)


def _get_column(model_class: type, col_name: str) -> sa.Column:
    """Get a column from a SQLAlchemy mapped class."""
    mapper = sa.inspect(model_class)
    for col in mapper.columns:
        if col.key == col_name:
            return col
    raise AssertionError(f"Column {col_name!r} not found on {model_class.__name__}")


def _get_constraints(model_class: type) -> list[str]:
    """Get all CheckConstraint SQL expressions for a table."""
    table = model_class.__table__
    checks = []
    for constraint in table.constraints:
        if isinstance(constraint, sa.CheckConstraint):
            checks.append(str(constraint.sqltext))
    return checks


class TestVectorColumns:
    """AC-SCHEMA-05: vector(384) columns on resumes, jobs, knowledge_chunks."""

    def test_resumes_has_embedding_column(self) -> None:
        col = _get_column(ResumeModel, "embedding")
        assert col is not None

    def test_jobs_has_embedding_column(self) -> None:
        col = _get_column(JobModel, "embedding")
        assert col is not None

    def test_knowledge_chunks_has_embedding_column(self) -> None:
        col = _get_column(KnowledgeChunkModel, "embedding")
        assert col is not None

    def test_resumes_embedding_is_vector_type(self) -> None:
        """The embedding column type must be a Vector type (pgvector)."""
        col = _get_column(ResumeModel, "embedding")
        # pgvector's type class is VECTOR (uppercase) in pgvector>=0.3
        type_name = type(col.type).__name__.upper()
        assert type_name == "VECTOR", f"Expected VECTOR, got {type_name}"

    def test_jobs_embedding_is_vector_type(self) -> None:
        col = _get_column(JobModel, "embedding")
        type_name = type(col.type).__name__.upper()
        assert type_name == "VECTOR", f"Expected VECTOR, got {type_name}"

    def test_knowledge_chunks_embedding_is_vector_type(self) -> None:
        col = _get_column(KnowledgeChunkModel, "embedding")
        type_name = type(col.type).__name__.upper()
        assert type_name == "VECTOR", f"Expected VECTOR, got {type_name}"

    def test_resumes_embedding_dim_384(self) -> None:
        """AC-SCHEMA-05: dimension exactly 384."""
        col = _get_column(ResumeModel, "embedding")
        assert col.type.dim == 384, f"Expected 384, got {col.type.dim}"

    def test_jobs_embedding_dim_384(self) -> None:
        col = _get_column(JobModel, "embedding")
        assert col.type.dim == 384, f"Expected 384, got {col.type.dim}"

    def test_knowledge_chunks_embedding_dim_384(self) -> None:
        col = _get_column(KnowledgeChunkModel, "embedding")
        assert col.type.dim == 384, f"Expected 384, got {col.type.dim}"


class TestCheckConstraints:
    """Enum CHECK constraints match data-models.md §0 value sets."""

    def test_users_theme_preference_check(self) -> None:
        constraints = _get_constraints(UserModel)
        assert any("theme_preference" in c for c in constraints)

    def test_resumes_parse_status_check(self) -> None:
        constraints = _get_constraints(ResumeModel)
        assert any("parse_status" in c for c in constraints)

    def test_jobs_source_check(self) -> None:
        constraints = _get_constraints(JobModel)
        assert any("source" in c for c in constraints)

    def test_knowledge_chunks_category_check(self) -> None:
        constraints = _get_constraints(KnowledgeChunkModel)
        assert any("category" in c for c in constraints)

    def test_ai_logs_feature_check(self) -> None:
        constraints = _get_constraints(AIRequestLogModel)
        assert any("feature" in c for c in constraints)

    def test_ai_logs_outcome_check(self) -> None:
        constraints = _get_constraints(AIRequestLogModel)
        assert any("outcome" in c for c in constraints)


class TestAllTablesRegistered:
    """All 11 ORM models are registered with the declarative base."""

    def test_eleven_tables_in_metadata(self) -> None:
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "users",
            "refresh_tokens",
            "profiles",
            "resumes",
            "resume_reviews",
            "profile_optimizations",
            "jobs",
            "job_match_runs",
            "job_matches",
            "knowledge_chunks",
            "ai_request_logs",
        }
        assert expected <= table_names, f"Missing tables: {expected - table_names}"

    def test_models_importable(self) -> None:
        models = [
            UserModel,
            RefreshTokenModel,
            ProfileModel,
            ResumeModel,
            ResumeReviewModel,
            ProfileOptimizationModel,
            JobModel,
            JobMatchRunModel,
            JobMatchModel,
            KnowledgeChunkModel,
            AIRequestLogModel,
        ]
        assert len(models) == 11
