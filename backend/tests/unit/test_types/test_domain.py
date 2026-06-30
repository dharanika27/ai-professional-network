"""Tests for app/types/domain.py — F001, F002, AC-SCHEMA-01, AC-SCHEMA-02,
AC-SCHEMA-07, AC-SCHEMA-08."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.types.domain import (
    AIRequestLog,
    Job,
    JobMatch,
    JobMatchRun,
    KnowledgeChunk,
    Profile,
    ProfileOptimization,
    RefreshToken,
    Resume,
    ResumeReview,
    User,
)
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

# ---------------------------------------------------------------------------
# Sample UUIDs and timestamps for consistent test data
# ---------------------------------------------------------------------------

_UID = uuid.UUID("8f1a3c2e-9b44-4d10-bb6e-1a2b3c4d5e6f")
_UID2 = uuid.UUID("2a2b2c2d-1111-4222-8333-444455556666")
_UID3 = uuid.UUID("c1c2c3c4-7777-4888-8999-aaaabbbbcccc")
_NOW = datetime(2026, 6, 30, 9, 15, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class TestUser:
    def _valid(self) -> dict:
        return {
            "id": _UID,
            "email": "asha.rao@example.com",
            "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$salt$hash",
            "theme_preference": ThemePreference.DARK,
            "created_at": _NOW,
            "updated_at": _NOW,
        }

    def test_valid_construction(self) -> None:
        user = User(**self._valid())
        assert user.email == "asha.rao@example.com"
        assert user.theme_preference == ThemePreference.DARK

    def test_invalid_theme_raises(self) -> None:
        """AC-SCHEMA-08: out-of-set enum must raise ValidationError."""
        data = self._valid()
        data["theme_preference"] = "rainbow"
        with pytest.raises(ValidationError):
            User(**data)

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07: extra fields must raise ValidationError."""
        data = self._valid()
        data["unknown_field"] = "hacker"
        with pytest.raises(ValidationError):
            User(**data)

    def test_default_theme_is_system(self) -> None:
        data = self._valid()
        del data["theme_preference"]
        user = User(**data)
        assert user.theme_preference == ThemePreference.SYSTEM


# ---------------------------------------------------------------------------
# RefreshToken
# ---------------------------------------------------------------------------


class TestRefreshToken:
    def _valid(self) -> dict:
        return {
            "id": _UID2,
            "user_id": _UID,
            "token_hash": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "expires_at": datetime(2026, 7, 30, tzinfo=UTC),
            "revoked": False,
            "rotated_to": None,
            "created_at": _NOW,
        }

    def test_valid_construction(self) -> None:
        rt = RefreshToken(**self._valid())
        assert rt.revoked is False
        assert rt.rotated_to is None

    def test_extra_field_rejected(self) -> None:
        data = self._valid()
        data["sneaky"] = "payload"
        with pytest.raises(ValidationError):
            RefreshToken(**data)


# ---------------------------------------------------------------------------
# Profile (AC-SCHEMA-02)
# ---------------------------------------------------------------------------


class TestProfile:
    def _valid(self) -> dict:
        return {
            "id": _UID2,
            "user_id": _UID,
            "full_name": "Asha Rao",
            "headline": "Final-year CS student | Aspiring Backend Engineer",
            "summary": "Building production-grade Python services...",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "education": [
                {
                    "institution": "PSG Tech",
                    "degree": "B.E. Computer Science",
                    "field": "CS",
                    "start_year": 2022,
                    "end_year": 2026,
                    "grade": "8.7 CGPA",
                }
            ],
            "experience": [],
            "certifications": [],
            "projects": [],
            "completion_percentage": 100,
            "created_at": _NOW,
            "updated_at": _NOW,
        }

    def test_valid_construction(self) -> None:
        profile = Profile(**self._valid())
        assert profile.skills == ["Python", "FastAPI", "PostgreSQL", "Docker"]
        assert isinstance(profile.skills, list)

    def test_skills_is_list_of_str(self) -> None:
        """AC-SCHEMA-02: skills is list[str]."""
        profile = Profile(**self._valid())
        for skill in profile.skills:
            assert isinstance(skill, str)

    def test_completion_percentage_valid_range(self) -> None:
        """AC-SCHEMA-02: completion_percentage int 0-100."""
        data = self._valid()
        data["completion_percentage"] = 0
        p = Profile(**data)
        assert p.completion_percentage == 0

    def test_completion_percentage_too_high_raises(self) -> None:
        """AC-SCHEMA-02: constructing with 150 raises ValidationError."""
        data = self._valid()
        data["completion_percentage"] = 150
        with pytest.raises(ValidationError):
            Profile(**data)

    def test_completion_percentage_negative_raises(self) -> None:
        data = self._valid()
        data["completion_percentage"] = -1
        with pytest.raises(ValidationError):
            Profile(**data)

    def test_headline_present(self) -> None:
        """AC-SCHEMA-02: headline field exists."""
        profile = Profile(**self._valid())
        assert profile.headline is not None

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07."""
        data = self._valid()
        data["malicious"] = "injection"
        with pytest.raises(ValidationError):
            Profile(**data)


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


class TestResume:
    def _valid(self) -> dict:
        return {
            "id": _UID3,
            "user_id": _UID,
            "original_filename": "asha_rao_resume.pdf",
            "mime_type": MimeType.PDF,
            "size_bytes": 184320,
            "file_hash": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            "storage_key": "resumes/8f1a3c2e/b94d27b9.pdf",
            "parse_status": ParseStatus.PARSED,
            "structured_content": None,
            "embedding": None,
            "parse_error": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }

    def test_valid_construction(self) -> None:
        resume = Resume(**self._valid())
        assert resume.mime_type == MimeType.PDF
        assert resume.parse_status == ParseStatus.PARSED

    def test_invalid_mime_type_raises(self) -> None:
        """AC-SCHEMA-08: mime_type rejects value not in two allowed MIME types."""
        data = self._valid()
        data["mime_type"] = "text/plain"
        with pytest.raises(ValidationError):
            Resume(**data)

    def test_invalid_parse_status_raises(self) -> None:
        """AC-SCHEMA-08: parse_status rejects value not in {pending,parsed,failed}."""
        data = self._valid()
        data["parse_status"] = "processing"
        with pytest.raises(ValidationError):
            Resume(**data)

    def test_size_too_large_raises(self) -> None:
        data = self._valid()
        data["size_bytes"] = 6_000_000
        with pytest.raises(ValidationError):
            Resume(**data)

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07."""
        data = self._valid()
        data["secret_field"] = "gotcha"
        with pytest.raises(ValidationError):
            Resume(**data)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


class TestJob:
    def _valid(self) -> dict:
        return {
            "id": uuid.UUID("f6f6f6f6-4444-4555-8666-777788889999"),
            "external_ref": "seed-000123",
            "title": "Junior Backend Engineer",
            "company": "Nimbus Cloud",
            "location": "Bengaluru, India (Hybrid)",
            "employment_type": "full_time",
            "description": "We are hiring a junior backend engineer...",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
            "seniority": "entry",
            "embedding": [0.041] * 384,
            "source": JobSource.SEED,
            "created_at": _NOW,
        }

    def test_valid_construction(self) -> None:
        job = Job(**self._valid())
        assert job.title == "Junior Backend Engineer"
        assert len(job.embedding) == 384

    def test_invalid_source_raises(self) -> None:
        data = self._valid()
        data["source"] = "unknown_source"
        with pytest.raises(ValidationError):
            Job(**data)


# ---------------------------------------------------------------------------
# JobMatchRun
# ---------------------------------------------------------------------------


class TestJobMatchRun:
    def test_valid_construction(self) -> None:
        run = JobMatchRun(
            id=_UID,
            user_id=_UID2,
            resume_id=_UID3,
            status=JobMatchRunStatus.PENDING,
            created_at=_NOW,
        )
        assert run.status == JobMatchRunStatus.PENDING

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            JobMatchRun(
                id=_UID,
                user_id=_UID2,
                resume_id=_UID3,
                status="unknown",  # type: ignore[arg-type]
                created_at=_NOW,
            )


# ---------------------------------------------------------------------------
# JobMatch
# ---------------------------------------------------------------------------


class TestJobMatch:
    def test_valid_construction(self) -> None:
        match = JobMatch(
            id=uuid.UUID("11111111-5555-4666-8777-888899990000"),
            run_id=uuid.UUID("22222222-6666-4777-8888-999900001111"),
            job_id=uuid.UUID("f6f6f6f6-4444-4555-8666-777788889999"),
            fit_score=82,
            fit_explanation="Strong Python/FastAPI alignment.",
            gaps=["Kubernetes exposure"],
            rank=1,
            created_at=_NOW,
        )
        assert match.fit_score == 82
        assert match.rank == 1

    def test_fit_score_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            JobMatch(
                id=_UID,
                run_id=_UID2,
                job_id=_UID3,
                fit_score=101,
                fit_explanation="Over limit.",
                gaps=[],
                rank=1,
                created_at=_NOW,
            )


# ---------------------------------------------------------------------------
# KnowledgeChunk
# ---------------------------------------------------------------------------


class TestKnowledgeChunk:
    def test_valid_construction(self) -> None:
        chunk = KnowledgeChunk(
            id=uuid.UUID("33333333-7777-4888-8999-aaaabbbbcccc"),
            source_file="ats_best_practices.md",
            category=KnowledgeCategory.ATS,
            chunk_index=1,
            content="Applicant tracking systems parse plain text...",
            content_hash="5d41402abc4b2a76b9719d911017c592",
            embedding=[0.020] * 384,
            created_at=_NOW,
        )
        assert chunk.category == KnowledgeCategory.ATS

    def test_invalid_category_raises(self) -> None:
        """AC-SCHEMA-08."""
        with pytest.raises(ValidationError):
            KnowledgeChunk(
                id=_UID,
                source_file="test.md",
                category="unknown_category",  # type: ignore[arg-type]
                chunk_index=0,
                content="test content",
                content_hash="abc123",
                embedding=[0.0] * 384,
                created_at=_NOW,
            )


# ---------------------------------------------------------------------------
# AIRequestLog (AC-SCHEMA-08 — feature and outcome enum rejection)
# ---------------------------------------------------------------------------


class TestAIRequestLog:
    def _valid(self) -> dict:
        return {
            "id": uuid.UUID("44444444-8888-4999-8aaa-bbbbccccdddd"),
            "request_id": uuid.UUID("55555555-9999-4aaa-8bbb-ccccddddeeee"),
            "user_id": _UID,
            "feature": AIFeature.RESUME_REVIEW,
            "model_id": "llama-3.3-70b-versatile",
            "outcome": AIOutcome.SUCCESS,
            "latency_ms": 4210,
            "input_tokens": 3120,
            "output_tokens": 880,
            "retry_count": 0,
            "created_at": _NOW,
        }

    def test_valid_construction(self) -> None:
        log = AIRequestLog(**self._valid())
        assert log.feature == AIFeature.RESUME_REVIEW
        assert log.outcome == AIOutcome.SUCCESS

    def test_invalid_feature_raises(self) -> None:
        """AC-SCHEMA-08: feature rejects out-of-set value."""
        data = self._valid()
        data["feature"] = "not_a_feature"
        with pytest.raises(ValidationError):
            AIRequestLog(**data)

    def test_invalid_outcome_raises(self) -> None:
        """AC-SCHEMA-08: outcome rejects out-of-set value."""
        data = self._valid()
        data["outcome"] = "magic_outcome"
        with pytest.raises(ValidationError):
            AIRequestLog(**data)

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07."""
        data = self._valid()
        data["extra_key"] = "extra_val"
        with pytest.raises(ValidationError):
            AIRequestLog(**data)


# ---------------------------------------------------------------------------
# All 11 entities exist (AC-SCHEMA-01)
# ---------------------------------------------------------------------------


class TestAllEntitiesExist:
    """AC-SCHEMA-01: Pydantic model classes exist for all 11 schema entities."""

    def test_eleven_domain_models_importable(self) -> None:
        entities = [
            User,
            RefreshToken,
            Profile,
            Resume,
            ResumeReview,
            ProfileOptimization,
            Job,
            JobMatchRun,
            JobMatch,
            KnowledgeChunk,
            AIRequestLog,
        ]
        assert len(entities) == 11

    def test_resume_review_construction(self) -> None:
        rr = ResumeReview(
            id=uuid.UUID("d4d4d4d4-2222-4333-8444-555566667777"),
            resume_id=_UID3,
            user_id=_UID,
            resume_file_hash="b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            status=ReviewStatus.COMPLETED,
            content=None,
            sources=[],
            model_id="llama-3.3-70b-versatile",
            created_at=_NOW,
        )
        assert rr.status == ReviewStatus.COMPLETED

    def test_profile_optimization_construction(self) -> None:
        po = ProfileOptimization(
            id=uuid.UUID("e5e5e5e5-3333-4444-8555-666677778888"),
            user_id=_UID,
            status=ReviewStatus.COMPLETED,
            content=None,
            sources=[],
            model_id=None,
            created_at=_NOW,
        )
        assert po.user_id == _UID
