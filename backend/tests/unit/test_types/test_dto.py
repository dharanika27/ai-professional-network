"""Tests for app/types/dto.py — F003, AC-SCHEMA-04, AC-SCHEMA-07.

Verifies that response DTOs NEVER expose password_hash, token_hash,
storage_key, or raw embedding vectors.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.types.dto import (
    AIRequestLogResponse,
    AuthSessionResponse,
    JobResponse,
    KnowledgeChunkResponse,
    ProfileOptimizationResponse,
    ProfileResponse,
    ResumeResponse,
    ResumeReviewResponse,
    UserResponse,
)
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

_UID = uuid.UUID("8f1a3c2e-9b44-4d10-bb6e-1a2b3c4d5e6f")
_UID2 = uuid.UUID("2a2b2c2d-1111-4222-8333-444455556666")
_UID3 = uuid.UUID("c1c2c3c4-7777-4888-8999-aaaabbbbcccc")
_NOW = datetime(2026, 6, 30, 9, 15, 0, tzinfo=UTC)

FORBIDDEN_KEYS = {"password_hash", "password", "token_hash", "storage_key", "embedding"}


def _dump_json(model: object) -> dict:
    """Serialize a Pydantic model to a dict via JSON round-trip."""
    import json

    from pydantic import BaseModel

    assert isinstance(model, BaseModel)
    return json.loads(model.model_dump_json())


# ---------------------------------------------------------------------------
# UserResponse — no password_hash
# ---------------------------------------------------------------------------


class TestUserResponse:
    def _valid(self) -> dict:
        return {
            "id": _UID,
            "email": "asha.rao@example.com",
            "theme_preference": ThemePreference.DARK,
            "created_at": _NOW,
            "updated_at": _NOW,
        }

    def test_no_password_hash_in_json(self) -> None:
        """AC-SCHEMA-04: UserResponse JSON must not contain password_hash."""
        dto = UserResponse(**self._valid())
        data = _dump_json(dto)
        assert "password_hash" not in data
        assert "password" not in data

    def test_no_forbidden_keys(self) -> None:
        dto = UserResponse(**self._valid())
        data = _dump_json(dto)
        found = set(data.keys()) & FORBIDDEN_KEYS
        assert not found, f"Forbidden keys found in UserResponse: {found}"

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07."""
        with pytest.raises(ValidationError):
            UserResponse(**self._valid(), password_hash="should_fail")


# ---------------------------------------------------------------------------
# ResumeResponse — no storage_key, no embedding
# ---------------------------------------------------------------------------


class TestResumeResponse:
    def _valid(self) -> dict:
        return {
            "id": _UID3,
            "user_id": _UID,
            "original_filename": "asha_rao_resume.pdf",
            "mime_type": MimeType.PDF,
            "size_bytes": 184320,
            "file_hash": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            "parse_status": ParseStatus.PARSED,
            "structured_content": None,
            "parse_error": None,
            "created_at": _NOW,
            "updated_at": _NOW,
        }

    def test_no_storage_key_in_json(self) -> None:
        """AC-SCHEMA-04: ResumeResponse must not contain storage_key."""
        dto = ResumeResponse(**self._valid())
        data = _dump_json(dto)
        assert "storage_key" not in data

    def test_no_embedding_in_json(self) -> None:
        """AC-SCHEMA-04: ResumeResponse must not contain embedding."""
        dto = ResumeResponse(**self._valid())
        data = _dump_json(dto)
        assert "embedding" not in data

    def test_no_forbidden_keys(self) -> None:
        dto = ResumeResponse(**self._valid())
        data = _dump_json(dto)
        found = set(data.keys()) & FORBIDDEN_KEYS
        assert not found, f"Forbidden keys found in ResumeResponse: {found}"


# ---------------------------------------------------------------------------
# ProfileResponse — no embedding
# ---------------------------------------------------------------------------


class TestProfileResponse:
    def _valid(self) -> dict:
        return {
            "id": _UID2,
            "user_id": _UID,
            "full_name": "Asha Rao",
            "headline": "Final-year CS student",
            "summary": "Building production-grade Python services...",
            "skills": ["Python", "FastAPI"],
            "education": [],
            "experience": [],
            "certifications": [],
            "projects": [],
            "completion_percentage": 42,
            "created_at": _NOW,
            "updated_at": _NOW,
        }

    def test_no_embedding_in_json(self) -> None:
        """AC-SCHEMA-04: ProfileResponse must not contain embedding."""
        dto = ProfileResponse(**self._valid())
        data = _dump_json(dto)
        assert "embedding" not in data

    def test_no_forbidden_keys(self) -> None:
        dto = ProfileResponse(**self._valid())
        data = _dump_json(dto)
        found = set(data.keys()) & FORBIDDEN_KEYS
        assert not found, f"Forbidden keys found in ProfileResponse: {found}"


# ---------------------------------------------------------------------------
# JobResponse — no embedding
# ---------------------------------------------------------------------------


class TestJobResponse:
    def test_no_embedding_in_json(self) -> None:
        """AC-SCHEMA-04: JobResponse must not contain embedding."""
        dto = JobResponse(
            id=uuid.UUID("f6f6f6f6-4444-4555-8666-777788889999"),
            external_ref="seed-000123",
            title="Junior Backend Engineer",
            company="Nimbus Cloud",
            location="Bengaluru, India (Hybrid)",
            employment_type="full_time",
            description="We are hiring...",
            skills=["Python", "FastAPI"],
            seniority="entry",
            source=JobSource.SEED,
            created_at=_NOW,
        )
        data = _dump_json(dto)
        assert "embedding" not in data


# ---------------------------------------------------------------------------
# KnowledgeChunkResponse — no embedding
# ---------------------------------------------------------------------------


class TestKnowledgeChunkResponse:
    def test_no_embedding_in_json(self) -> None:
        dto = KnowledgeChunkResponse(
            id=uuid.UUID("33333333-7777-4888-8999-aaaabbbbcccc"),
            source_file="ats_best_practices.md",
            category=KnowledgeCategory.ATS,
            chunk_index=1,
            content="ATS tips...",
            content_hash="abc123",
            created_at=_NOW,
        )
        data = _dump_json(dto)
        assert "embedding" not in data


# ---------------------------------------------------------------------------
# AuthSessionResponse — no token_hash in body
# ---------------------------------------------------------------------------


class TestAuthSessionResponse:
    def test_no_token_hash_in_json(self) -> None:
        user_dto = UserResponse(
            id=_UID,
            email="asha.rao@example.com",
            theme_preference=ThemePreference.DARK,
            created_at=_NOW,
            updated_at=_NOW,
        )
        auth_resp = AuthSessionResponse(
            access_token="eyJ...",
            token_type="bearer",
            user=user_dto,
        )
        data = _dump_json(auth_resp)
        assert "token_hash" not in json.dumps(data)


# ---------------------------------------------------------------------------
# Aggregate: all response DTOs lack all four forbidden columns
# ---------------------------------------------------------------------------


class TestAllResponseDTOsForbiddenFields:
    """AC-SCHEMA-04: Comprehensive check across all response DTOs."""

    def test_resume_review_response_no_forbidden(self) -> None:
        dto = ResumeReviewResponse(
            id=uuid.UUID("d4d4d4d4-2222-4333-8444-555566667777"),
            resume_id=_UID3,
            user_id=_UID,
            resume_file_hash="abc123",
            status=ReviewStatus.COMPLETED,
            content=None,
            sources=[],
            model_id=None,
            created_at=_NOW,
        )
        data = _dump_json(dto)
        assert "storage_key" not in json.dumps(data)
        assert "embedding" not in json.dumps(data)
        assert "token_hash" not in json.dumps(data)
        assert "password_hash" not in json.dumps(data)

    def test_profile_optimization_response_no_forbidden(self) -> None:
        dto = ProfileOptimizationResponse(
            id=uuid.UUID("e5e5e5e5-3333-4444-8555-666677778888"),
            user_id=_UID,
            status=ReviewStatus.COMPLETED,
            content=None,
            sources=[],
            model_id=None,
            created_at=_NOW,
        )
        data = _dump_json(dto)
        assert "embedding" not in json.dumps(data)

    def test_ai_request_log_response_no_forbidden(self) -> None:
        dto = AIRequestLogResponse(
            id=uuid.UUID("44444444-8888-4999-8aaa-bbbbccccdddd"),
            request_id=uuid.UUID("55555555-9999-4aaa-8bbb-ccccddddeeee"),
            user_id=_UID,
            feature=AIFeature.RESUME_REVIEW,
            model_id="llama-3.3-70b-versatile",
            outcome=AIOutcome.SUCCESS,
            latency_ms=4210,
            input_tokens=3120,
            output_tokens=880,
            retry_count=0,
            created_at=_NOW,
        )
        data = _dump_json(dto)
        found = set(data.keys()) & FORBIDDEN_KEYS
        assert not found
