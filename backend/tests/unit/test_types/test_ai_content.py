"""Tests for app/types/ai.py — AI content schemas F001, AC-SCHEMA-07."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.types.ai import ProfileOptimizationContent, ResumeReviewContent
from app.types.structured import ReviewItem


class TestResumeReviewContent:
    def _valid(self) -> dict:
        return {
            "overall_summary": "Strong technical base with clear project impact.",
            "strengths": [ReviewItem(text="Clear project impact", source_id="ats-1")],
            "weaknesses": [],
            "ats_issues": [],
            "suggestions": [],
        }

    def test_valid_construction(self) -> None:
        rc = ResumeReviewContent(**self._valid())
        assert rc.overall_summary.startswith("Strong")
        assert len(rc.strengths) == 1

    def test_empty_lists_valid(self) -> None:
        rc = ResumeReviewContent(
            overall_summary="Good resume.",
            strengths=[],
            weaknesses=[],
            ats_issues=[],
            suggestions=[],
        )
        assert rc.weaknesses == []

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07."""
        data = self._valid()
        data["injected_field"] = "payload"
        with pytest.raises(ValidationError):
            ResumeReviewContent(**data)

    def test_missing_overall_summary_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResumeReviewContent(strengths=[], weaknesses=[], ats_issues=[], suggestions=[])


class TestProfileOptimizationContent:
    def _valid(self) -> dict:
        return {
            "headline_suggestions": [
                ReviewItem(
                    text="Backend Engineer | Python · FastAPI · pgvector", source_id="profile-2"
                )
            ],
            "summary_suggestion": ReviewItem(
                text="Lead with role + top skills.", source_id="profile-2"
            ),
            "missing_skills": ["CI/CD"],
            "section_suggestions": [],
        }

    def test_valid_construction(self) -> None:
        poc = ProfileOptimizationContent(**self._valid())
        assert "CI/CD" in poc.missing_skills
        assert poc.summary_suggestion is not None

    def test_summary_suggestion_optional(self) -> None:
        poc = ProfileOptimizationContent(
            headline_suggestions=[],
            missing_skills=[],
            section_suggestions=[],
        )
        assert poc.summary_suggestion is None

    def test_extra_field_rejected(self) -> None:
        data = self._valid()
        data["extra_field"] = "value"
        with pytest.raises(ValidationError):
            ProfileOptimizationContent(**data)
