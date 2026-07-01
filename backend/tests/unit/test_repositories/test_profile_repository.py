"""Unit tests for profile_repository.py — F024/F025/F026/F027.

No live DB required. Tests exercise:
  - compute_completion_percentage pure function (all combinations)
  - update_profile calls session.flush() (mock)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from app.repositories.profile_repository import (
    ProfileUpdateData,
    compute_completion_percentage,
    update_profile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=UTC)


def _make_profile_row(
    *,
    user_id: uuid.UUID | None = None,
    headline: str | None = None,
    summary: str | None = None,
    skills: list[Any] | None = None,
    education: list[Any] | None = None,
    experience: list[Any] | None = None,
    certifications: list[Any] | None = None,
    projects: list[Any] | None = None,
    completion_percentage: int = 0,
) -> MagicMock:
    """Return a MagicMock that looks like a ProfileModel ORM row."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.user_id = user_id or uuid.uuid4()
    row.full_name = None
    row.headline = headline
    row.summary = summary
    row.skills = skills if skills is not None else []
    row.education = education if education is not None else []
    row.experience = experience if experience is not None else []
    row.certifications = certifications if certifications is not None else []
    row.projects = projects if projects is not None else []
    row.completion_percentage = completion_percentage
    row.created_at = _NOW
    row.updated_at = _NOW
    return row


# ---------------------------------------------------------------------------
# compute_completion_percentage — pure function
# ---------------------------------------------------------------------------


class TestComputeCompletionPercentage:
    """F026 / AC-SCHEMA-B04 / AC-BEHAV-B07."""

    def test_all_sections_populated_returns_100(self) -> None:
        result = compute_completion_percentage(
            headline="Engineer",
            summary="10 years experience",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[{"name": "AWS"}],
            projects=[{"title": "MyApp"}],
        )
        assert result == 100

    def test_none_populated_returns_0(self) -> None:
        result = compute_completion_percentage(
            headline=None,
            summary=None,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 0

    def test_empty_strings_not_counted(self) -> None:
        """Empty string headline/summary must not count as populated."""
        result = compute_completion_percentage(
            headline="",
            summary="",
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 0

    def test_three_sections_populated(self) -> None:
        """round(100 * 3 / 7) == 43"""
        result = compute_completion_percentage(
            headline="Engineer",
            summary="Summary text",
            skills=["Python"],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 43

    def test_one_section_populated_headline_only(self) -> None:
        """round(100 * 1 / 7) == 14"""
        result = compute_completion_percentage(
            headline="Engineer",
            summary=None,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 14

    def test_two_sections_populated(self) -> None:
        """round(100 * 2 / 7) == 29"""
        result = compute_completion_percentage(
            headline="Engineer",
            summary=None,
            skills=["Go"],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 29

    def test_four_sections_populated(self) -> None:
        """round(100 * 4 / 7) == 57"""
        result = compute_completion_percentage(
            headline="Engineer",
            summary="Text",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 57

    def test_five_sections_populated(self) -> None:
        """round(100 * 5 / 7) == 71"""
        result = compute_completion_percentage(
            headline="Engineer",
            summary="Text",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[],
            projects=[],
        )
        assert result == 71

    def test_six_sections_populated(self) -> None:
        """round(100 * 6 / 7) == 86"""
        result = compute_completion_percentage(
            headline="Engineer",
            summary="Text",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[{"name": "AWS"}],
            projects=[],
        )
        assert result == 86

    def test_skills_with_multiple_items(self) -> None:
        """Multiple items in skills still counts as 1 section."""
        result = compute_completion_percentage(
            headline=None,
            summary=None,
            skills=["Python", "Go", "Rust"],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 14  # round(100 * 1 / 7) == 14

    def test_summary_only_populated(self) -> None:
        """Only summary populated → 14."""
        result = compute_completion_percentage(
            headline=None,
            summary="I am a developer",
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        assert result == 14

    def test_projects_only_populated(self) -> None:
        """Only projects populated → 14."""
        result = compute_completion_percentage(
            headline=None,
            summary=None,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[{"title": "Demo"}],
        )
        assert result == 14


# ---------------------------------------------------------------------------
# update_profile — verify session.flush() is called
# ---------------------------------------------------------------------------


class TestUpdateProfileCallsFlush:
    """F025 / AC-BEHAV-B06: update_profile must call session.flush()."""

    def _make_session_with_existing_row(self, user_id: uuid.UUID) -> MagicMock:
        """Return a mock Session whose scalars().first() returns a profile row."""
        session = MagicMock()
        row = _make_profile_row(user_id=user_id)
        session.scalars.return_value.first.return_value = row
        return session

    def test_update_profile_calls_session_flush(self) -> None:
        user_id = uuid.uuid4()
        session = self._make_session_with_existing_row(user_id)

        data = ProfileUpdateData(
            headline="Senior Engineer",
            summary="10 years",
            skills=["Python"],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )

        update_profile(session, user_id, data)

        session.flush.assert_called_once()

    def test_update_profile_calls_flush_when_row_missing(self) -> None:
        """If no row exists yet, update_profile creates one and still flushes."""
        user_id = uuid.uuid4()
        session = MagicMock()
        # First call to scalars().first() returns None (no row yet)
        session.scalars.return_value.first.return_value = None

        # When flush() is called, simulate the DB assigning an id to the new row
        def _side_effect_flush() -> None:
            # After flush, the row passed to session.add() needs an id.
            # Reach into the call args to set it on the real ProfileModel instance.
            if session.add.call_args is not None:
                added_row = session.add.call_args[0][0]
                added_row.id = uuid.uuid4()
                added_row.created_at = _NOW
                added_row.updated_at = _NOW

        session.flush.side_effect = _side_effect_flush

        data = ProfileUpdateData(headline="New", summary=None)
        update_profile(session, user_id, data)

        session.flush.assert_called_once()

    def test_update_profile_does_not_commit(self) -> None:
        """CRITICAL: update_profile must NEVER call session.commit()."""
        user_id = uuid.uuid4()
        session = self._make_session_with_existing_row(user_id)

        data = ProfileUpdateData(headline="Test")
        update_profile(session, user_id, data)

        session.commit.assert_not_called()

    def test_update_profile_does_not_rollback(self) -> None:
        """CRITICAL: update_profile must NEVER call session.rollback()."""
        user_id = uuid.uuid4()
        session = self._make_session_with_existing_row(user_id)

        data = ProfileUpdateData(headline="Test")
        update_profile(session, user_id, data)

        session.rollback.assert_not_called()
