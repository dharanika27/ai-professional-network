"""Tests for app/types/enums.py — F001, AC-SCHEMA-08."""

from __future__ import annotations

from app.types.enums import (
    ALLOWED_MIME_TYPES,
    MIME_DOCX,
    MIME_PDF,
    AIFeature,
    AIOutcome,
    JobSource,
    KnowledgeCategory,
    MimeType,
    ParseStatus,
    ReviewStatus,
    ThemePreference,
)


class TestThemePreference:
    """ThemePreference enum value-set conformance."""

    def test_valid_values_exist(self) -> None:
        assert ThemePreference.SYSTEM == "system"
        assert ThemePreference.LIGHT == "light"
        assert ThemePreference.DARK == "dark"

    def test_all_three_members(self) -> None:
        assert set(ThemePreference) == {
            ThemePreference.SYSTEM,
            ThemePreference.LIGHT,
            ThemePreference.DARK,
        }

    def test_is_str(self) -> None:
        assert isinstance(ThemePreference.DARK, str)


class TestParseStatus:
    """ParseStatus enum — resume.parse_status value set."""

    def test_valid_values(self) -> None:
        assert ParseStatus.PENDING == "pending"
        assert ParseStatus.PARSED == "parsed"
        assert ParseStatus.FAILED == "failed"

    def test_all_members(self) -> None:
        assert set(ParseStatus) == {
            ParseStatus.PENDING,
            ParseStatus.PARSED,
            ParseStatus.FAILED,
        }


class TestReviewStatus:
    def test_valid_values(self) -> None:
        assert ReviewStatus.PENDING == "pending"
        assert ReviewStatus.COMPLETED == "completed"
        assert ReviewStatus.FAILED == "failed"


class TestAIFeature:
    def test_all_four_features(self) -> None:
        assert AIFeature.RESUME_STRUCTURING == "resume_structuring"
        assert AIFeature.RESUME_REVIEW == "resume_review"
        assert AIFeature.PROFILE_OPTIMIZATION == "profile_optimization"
        assert AIFeature.JOB_MATCHING == "job_matching"

    def test_exactly_four_members(self) -> None:
        assert len(list(AIFeature)) == 4


class TestAIOutcome:
    def test_all_six_outcomes(self) -> None:
        assert AIOutcome.SUCCESS == "success"
        assert AIOutcome.RETRY_SUCCESS == "retry_success"
        assert AIOutcome.FAILED == "failed"
        assert AIOutcome.TIMEOUT == "timeout"
        assert AIOutcome.INVALID_SCHEMA == "invalid_schema"
        assert AIOutcome.RATE_LIMITED == "rate_limited"

    def test_exactly_six_members(self) -> None:
        assert len(list(AIOutcome)) == 6


class TestKnowledgeCategory:
    def test_all_five_categories(self) -> None:
        assert KnowledgeCategory.ATS == "ats"
        assert KnowledgeCategory.RESUME == "resume"
        assert KnowledgeCategory.PROFILE == "profile"
        assert KnowledgeCategory.INTERVIEW == "interview"
        assert KnowledgeCategory.CAREER == "career"


class TestMimeType:
    def test_pdf_value(self) -> None:
        assert MimeType.PDF == "application/pdf"

    def test_docx_value(self) -> None:
        assert (
            MimeType.DOCX
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_constants_match_enum(self) -> None:
        assert MIME_PDF == MimeType.PDF
        assert MIME_DOCX == MimeType.DOCX

    def test_allowed_set_contains_both(self) -> None:
        assert MIME_PDF in ALLOWED_MIME_TYPES
        assert MIME_DOCX in ALLOWED_MIME_TYPES
        assert len(ALLOWED_MIME_TYPES) == 2


class TestJobSource:
    def test_values(self) -> None:
        assert JobSource.SEED == "seed"
        assert JobSource.API == "api"
