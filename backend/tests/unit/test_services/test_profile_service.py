"""Unit tests for profile_service.py (E3-S2).

The repository is mocked so these tests exercise service-layer logic only:
ownership enforcement, field validation, skill normalization, and
incomplete_sections computation.

Covers AC-BEHAV-C20 (skill normalization) and the ownership/validation
guarantees of the profile service.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.repositories import profile_repository
from app.services import profile_service
from app.services.profile_service import (
    ProfileAuthorizationError,
    ProfileUpdateRequest,
    ProfileValidationError,
)
from app.types.domain import Profile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    user_id: uuid.UUID,
    *,
    headline: str | None = None,
    summary: str | None = None,
    skills: list[str] | None = None,
    education: list[dict[str, Any]] | None = None,
    experience: list[dict[str, Any]] | None = None,
    certifications: list[dict[str, Any]] | None = None,
    projects: list[dict[str, Any]] | None = None,
    completion_percentage: int = 0,
) -> Profile:
    """Build a Profile domain object for stubbing repository returns."""
    now = datetime.now(UTC)
    return Profile(
        id=uuid.uuid4(),
        user_id=user_id,
        full_name=None,
        headline=headline,
        summary=summary,
        skills=skills or [],
        education=education or [],
        experience=experience or [],
        certifications=certifications or [],
        projects=projects or [],
        completion_percentage=completion_percentage,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def settings() -> Any:
    """A stand-in Settings object; the profile service does not read fields."""
    return MagicMock()


@pytest.fixture()
def session() -> Any:
    """A stand-in SQLAlchemy Session — never touched directly by the service."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    def test_blank_profile_has_all_sections_incomplete(
        self, monkeypatch: pytest.MonkeyPatch, session: Any
    ) -> None:
        user_id = uuid.uuid4()
        monkeypatch.setattr(
            profile_repository,
            "get_profile_by_user_id",
            lambda s, uid: _make_profile(uid),
        )

        dto = profile_service.get_profile(session, user_id, user_id)

        assert dto.profile.user_id == user_id
        assert set(dto.incomplete_sections) == {
            "headline",
            "summary",
            "skills",
            "education",
            "experience",
            "certifications",
            "projects",
        }

    def test_mismatched_user_id_raises_authorization_error(self, session: Any) -> None:
        requester = uuid.uuid4()
        owner = uuid.uuid4()

        with pytest.raises(ProfileAuthorizationError):
            profile_service.get_profile(session, requester, owner)

    def test_completed_profile_has_no_incomplete_sections(
        self, monkeypatch: pytest.MonkeyPatch, session: Any
    ) -> None:
        user_id = uuid.uuid4()
        full = _make_profile(
            user_id,
            headline="Engineer",
            summary="Experienced",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[{"name": "AWS"}],
            projects=[{"title": "Demo"}],
            completion_percentage=100,
        )
        monkeypatch.setattr(profile_repository, "get_profile_by_user_id", lambda s, uid: full)

        dto = profile_service.get_profile(session, user_id, user_id)

        assert dto.incomplete_sections == []


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    def test_valid_update_normalizes_skills_and_returns_dto(
        self, monkeypatch: pytest.MonkeyPatch, session: Any, settings: Any
    ) -> None:
        user_id = uuid.uuid4()
        captured: dict[str, Any] = {}

        def fake_update(
            s: Any, uid: uuid.UUID, data: profile_repository.ProfileUpdateData
        ) -> Profile:
            captured["data"] = data
            return _make_profile(uid, skills=data.skills, completion_percentage=14)

        monkeypatch.setattr(profile_repository, "update_profile", fake_update)

        req = ProfileUpdateRequest(skills=["Python", " Python ", "Go"])
        dto = profile_service.update_profile(session, user_id, user_id, req, settings)

        # skills normalized before hitting the repository
        assert captured["data"].skills == ["Python", "Go"]
        assert dto.profile.skills == ["Python", "Go"]

    def test_headline_too_long_raises_validation_error(self, session: Any, settings: Any) -> None:
        user_id = uuid.uuid4()
        req = ProfileUpdateRequest(headline="x" * 161)

        with pytest.raises(ProfileValidationError):
            profile_service.update_profile(session, user_id, user_id, req, settings)

    def test_summary_too_long_raises_validation_error(self, session: Any, settings: Any) -> None:
        user_id = uuid.uuid4()
        req = ProfileUpdateRequest(summary="x" * 2001)

        with pytest.raises(ProfileValidationError):
            profile_service.update_profile(session, user_id, user_id, req, settings)

    def test_full_name_too_long_raises_validation_error(self, session: Any, settings: Any) -> None:
        user_id = uuid.uuid4()
        req = ProfileUpdateRequest(full_name="x" * 121)

        with pytest.raises(ProfileValidationError):
            profile_service.update_profile(session, user_id, user_id, req, settings)

    def test_empty_skills_list_raises_validation_error(self, session: Any, settings: Any) -> None:
        user_id = uuid.uuid4()
        req = ProfileUpdateRequest(skills=[])

        with pytest.raises(ProfileValidationError):
            profile_service.update_profile(session, user_id, user_id, req, settings)

    def test_skill_dedup_case_preserved(
        self, monkeypatch: pytest.MonkeyPatch, session: Any, settings: Any
    ) -> None:
        user_id = uuid.uuid4()
        captured: dict[str, Any] = {}

        def fake_update(
            s: Any, uid: uuid.UUID, data: profile_repository.ProfileUpdateData
        ) -> Profile:
            captured["data"] = data
            return _make_profile(uid, skills=data.skills)

        monkeypatch.setattr(profile_repository, "update_profile", fake_update)

        req = ProfileUpdateRequest(skills=["Python", " Python ", "Python"])
        profile_service.update_profile(session, user_id, user_id, req, settings)

        assert captured["data"].skills == ["Python"]

    def test_mismatched_user_id_raises_authorization_error(
        self, session: Any, settings: Any
    ) -> None:
        requester = uuid.uuid4()
        owner = uuid.uuid4()
        req = ProfileUpdateRequest(headline="Engineer")

        with pytest.raises(ProfileAuthorizationError):
            profile_service.update_profile(session, requester, owner, req, settings)

    def test_validation_error_raised_before_repository_call(
        self, monkeypatch: pytest.MonkeyPatch, session: Any, settings: Any
    ) -> None:
        user_id = uuid.uuid4()
        repo_mock = MagicMock()
        monkeypatch.setattr(profile_repository, "update_profile", repo_mock)

        req = ProfileUpdateRequest(headline="x" * 200)
        with pytest.raises(ProfileValidationError):
            profile_service.update_profile(session, user_id, user_id, req, settings)

        repo_mock.assert_not_called()

    def test_skill_normalization_strip_dedup_case_preserved(
        self, monkeypatch: pytest.MonkeyPatch, session: Any, settings: Any
    ) -> None:
        """['  FastAPI  ', 'FastAPI', 'fastapi'] -> ['FastAPI', 'fastapi']."""
        user_id = uuid.uuid4()
        captured: dict[str, Any] = {}

        def fake_update(
            s: Any, uid: uuid.UUID, data: profile_repository.ProfileUpdateData
        ) -> Profile:
            captured["data"] = data
            return _make_profile(uid, skills=data.skills)

        monkeypatch.setattr(profile_repository, "update_profile", fake_update)

        req = ProfileUpdateRequest(skills=["  FastAPI  ", "FastAPI", "fastapi"])
        profile_service.update_profile(session, user_id, user_id, req, settings)

        assert captured["data"].skills == ["FastAPI", "fastapi"]

    def test_skill_normalization_drops_empty_after_strip(
        self, monkeypatch: pytest.MonkeyPatch, session: Any, settings: Any
    ) -> None:
        """Whitespace-only skills collapse away; if all empty -> validation error."""
        user_id = uuid.uuid4()
        req = ProfileUpdateRequest(skills=["   ", "\t", ""])

        with pytest.raises(ProfileValidationError):
            profile_service.update_profile(session, user_id, user_id, req, settings)
