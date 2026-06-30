"""Tests for app/types/structured.py — F005, AC-SCHEMA-03, AC-SCHEMA-07."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.types.structured import (
    CertificationItem,
    Citation,
    ContactInfo,
    EducationItem,
    ExperienceItem,
    ProjectItem,
    ReviewItem,
    StructuredResume,
)

# ---------------------------------------------------------------------------
# ContactInfo
# ---------------------------------------------------------------------------


class TestContactInfo:
    def test_valid_minimal(self) -> None:
        """Only links is required (can be empty list)."""
        ci = ContactInfo(links=[])
        assert ci.links == []
        assert ci.full_name is None

    def test_valid_full(self) -> None:
        ci = ContactInfo(
            full_name="Asha Rao",
            email="asha.rao@example.com",
            phone="+91-9876543210",
            location="Chennai, India",
            links=["https://github.com/asha", "https://linkedin.com/in/asha"],
        )
        assert ci.full_name == "Asha Rao"
        assert len(ci.links) == 2

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-07."""
        with pytest.raises(ValidationError):
            ContactInfo(links=[], unknown_field="gotcha")


# ---------------------------------------------------------------------------
# EducationItem
# ---------------------------------------------------------------------------


class TestEducationItem:
    def test_valid_minimal(self) -> None:
        edu = EducationItem(institution="PSG Tech")
        assert edu.institution == "PSG Tech"
        assert edu.degree is None

    def test_valid_full(self) -> None:
        edu = EducationItem(
            institution="PSG Tech",
            degree="B.E. Computer Science",
            field="CS",
            start_year=2022,
            end_year=2026,
            grade="8.7 CGPA",
        )
        assert edu.grade == "8.7 CGPA"

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EducationItem(institution="PSG Tech", gpa_extra=9.0)


# ---------------------------------------------------------------------------
# ExperienceItem
# ---------------------------------------------------------------------------


class TestExperienceItem:
    def test_valid(self) -> None:
        exp = ExperienceItem(
            company="Acme Labs",
            title="Backend Intern",
            start_date="2025-05",
            end_date="2025-08",
            current=False,
            description="Built REST APIs.",
        )
        assert exp.company == "Acme Labs"
        assert exp.current is False

    def test_current_defaults_false(self) -> None:
        exp = ExperienceItem(company="Corp", title="Engineer")
        assert exp.current is False

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExperienceItem(company="Corp", title="Engineer", current=False, hacker="xss")


# ---------------------------------------------------------------------------
# CertificationItem
# ---------------------------------------------------------------------------


class TestCertificationItem:
    def test_valid(self) -> None:
        cert = CertificationItem(name="AWS Cloud Practitioner", issuer="AWS", issued_date="2025-03")
        assert cert.name == "AWS Cloud Practitioner"

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CertificationItem(name="AWS", score=100)


# ---------------------------------------------------------------------------
# ProjectItem
# ---------------------------------------------------------------------------


class TestProjectItem:
    def test_valid_minimal(self) -> None:
        proj = ProjectItem(name="ResumeRAG")
        assert proj.technologies == []

    def test_valid_full(self) -> None:
        proj = ProjectItem(
            name="ResumeRAG",
            description="RAG resume reviewer",
            url="https://github.com/asha/resumerag",
            technologies=["Python", "pgvector"],
        )
        assert "pgvector" in proj.technologies

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProjectItem(name="proj", technologies=[], internal_notes="todo")


# ---------------------------------------------------------------------------
# StructuredResume (AC-SCHEMA-03 — exactly the BRD six-key schema)
# ---------------------------------------------------------------------------


class TestStructuredResume:
    def _valid(self) -> dict:
        return {
            "contact": ContactInfo(
                full_name="Asha Rao",
                email="asha.rao@example.com",
                links=[],
            ),
            "skills": ["Python", "FastAPI"],
            "education": [EducationItem(institution="PSG Tech", degree="B.E. CS")],
            "experience": [],
            "certifications": [],
            "projects": [],
        }

    def test_valid_construction(self) -> None:
        """AC-SCHEMA-03: valid sample StructuredResume."""
        sr = StructuredResume(**self._valid())
        assert isinstance(sr.contact, ContactInfo)
        assert "Python" in sr.skills

    def test_has_exactly_six_keys(self) -> None:
        """AC-SCHEMA-03: exactly {contact, skills, education, experience, certifications, projects}."""
        sr = StructuredResume(**self._valid())
        fields = set(sr.model_fields.keys())
        expected = {"contact", "skills", "education", "experience", "certifications", "projects"}
        assert fields == expected

    def test_extra_field_rejected(self) -> None:
        """AC-SCHEMA-03 + AC-SCHEMA-07: rejects unknown keys."""
        data = self._valid()
        data["secret_data"] = "injected"
        with pytest.raises(ValidationError):
            StructuredResume(**data)

    def test_missing_required_field_raises(self) -> None:
        data = self._valid()
        del data["contact"]
        with pytest.raises(ValidationError):
            StructuredResume(**data)

    def test_nested_education_item_typed(self) -> None:
        sr = StructuredResume(**self._valid())
        assert all(isinstance(e, EducationItem) for e in sr.education)

    def test_skills_is_list_of_strings(self) -> None:
        sr = StructuredResume(**self._valid())
        assert all(isinstance(s, str) for s in sr.skills)


# ---------------------------------------------------------------------------
# ReviewItem and Citation
# ---------------------------------------------------------------------------


class TestReviewItem:
    def test_valid(self) -> None:
        ri = ReviewItem(text="Use measurable outcomes.", source_id="ats-1")
        assert ri.text == "Use measurable outcomes."

    def test_source_id_optional(self) -> None:
        ri = ReviewItem(text="Improve your summary.")
        assert ri.source_id is None

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReviewItem(text="Good", extra_field="bad")


class TestCitation:
    def test_valid(self) -> None:
        cit = Citation(
            source_id="ats-1", source_file="ats_best_practices.md", snippet="Short excerpt."
        )
        assert cit.source_id == "ats-1"

    def test_snippet_optional(self) -> None:
        cit = Citation(source_id="ats-1", source_file="ats.md")
        assert cit.snippet is None

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Citation(source_id="x", source_file="y.md", hacker_field=True)
