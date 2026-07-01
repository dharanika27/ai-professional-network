"""Integration tests for profile_service.py against a live DB (E3-S2).

Requires TEST_DATABASE_URL pointing to a running PostgreSQL instance.
The db_session fixture rolls back after each test, so writes are reverted.

Verifies that the service layer composes correctly with the real repository:
blank-profile creation, persistence + completion recompute, and ownership.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.db.models import UserModel
from app.services import profile_service
from app.services.profile_service import (
    ProfileAuthorizationError,
    ProfileUpdateRequest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_user(session: Session) -> UserModel:
    """Create and flush a UserModel; returns the flushed row."""
    user = UserModel(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture()
def settings() -> object:
    """Profile service does not read settings fields."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_profile — blank creation
# ---------------------------------------------------------------------------


def test_get_profile_creates_blank_profile(db_session: Session) -> None:
    user = _create_user(db_session)

    dto = profile_service.get_profile(db_session, user.id, user.id)

    assert dto.profile.user_id == user.id
    assert dto.profile.completion_percentage == 0
    assert set(dto.incomplete_sections) == {
        "headline",
        "summary",
        "skills",
        "education",
        "experience",
        "certifications",
        "projects",
    }


# ---------------------------------------------------------------------------
# update_profile — persistence + completion recompute
# ---------------------------------------------------------------------------


def test_update_profile_persists_and_recomputes_completion(
    db_session: Session, settings: object
) -> None:
    user = _create_user(db_session)

    req = ProfileUpdateRequest(
        headline="Senior Engineer",
        summary="Experienced backend developer",
        skills=["Python", " Python ", "Go"],
        education=[{"degree": "BSc"}],
        experience=[{"company": "Acme"}],
        certifications=[{"name": "AWS"}],
        projects=[{"title": "Demo"}],
    )

    dto = profile_service.update_profile(db_session, user.id, user.id, req, settings)

    assert dto.profile.completion_percentage == 100
    assert dto.incomplete_sections == []
    # skills were normalized before persistence
    assert dto.profile.skills == ["Python", "Go"]

    # re-read through the service confirms persistence
    reread = profile_service.get_profile(db_session, user.id, user.id)
    assert reread.profile.headline == "Senior Engineer"
    assert reread.profile.skills == ["Python", "Go"]
    assert reread.profile.completion_percentage == 100


def test_update_profile_partial_completion(db_session: Session, settings: object) -> None:
    user = _create_user(db_session)

    req = ProfileUpdateRequest(headline="Engineer", summary="Text", skills=["Python"])
    dto = profile_service.update_profile(db_session, user.id, user.id, req, settings)

    # 3 of 7 sections populated -> round(100 * 3/7) == 43
    assert dto.profile.completion_percentage == 43
    assert set(dto.incomplete_sections) == {
        "education",
        "experience",
        "certifications",
        "projects",
    }


# ---------------------------------------------------------------------------
# Ownership enforcement
# ---------------------------------------------------------------------------


def test_get_profile_rejects_wrong_user(db_session: Session) -> None:
    owner = _create_user(db_session)
    other = _create_user(db_session)

    with pytest.raises(ProfileAuthorizationError):
        profile_service.get_profile(db_session, other.id, owner.id)


def test_update_profile_rejects_wrong_user(db_session: Session, settings: object) -> None:
    owner = _create_user(db_session)
    other = _create_user(db_session)

    req = ProfileUpdateRequest(headline="Hijack attempt")
    with pytest.raises(ProfileAuthorizationError):
        profile_service.update_profile(db_session, other.id, owner.id, req, settings)
