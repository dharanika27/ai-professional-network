"""Integration tests for profile_repository.py against live DB.

Requires TEST_DATABASE_URL pointing to a running PostgreSQL instance.
Each test uses the db_session fixture which rolls back after the test,
so all writes are automatically reverted — no cleanup needed.

Tests cover:
  F024/AC-BEHAV-B05 — get_profile_by_user_id upsert semantics
  F025/AC-BEHAV-B06 — update_profile persists all 7 sections
  F026/AC-SCHEMA-B04/AC-BEHAV-B07 — completion_percentage recomputed
  F027/AC-BEHAV-B08 — profile isolation between users
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ProfileModel, UserModel
from app.repositories.profile_repository import (
    ProfileUpdateData,
    get_profile_by_user_id,
    update_profile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_user(session: Session, email: str | None = None) -> UserModel:
    """Create and flush a UserModel. Returns the flushed row."""
    email = email or f"test-{uuid.uuid4().hex[:8]}@example.com"
    user = UserModel(
        email=email,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehash",
    )
    session.add(user)
    session.flush()
    return user


def _count_profiles_for(session: Session, user_id: uuid.UUID) -> int:
    """Return the number of profile rows for a given user_id."""
    result = session.execute(select(func.count()).where(ProfileModel.user_id == user_id))
    count: int = result.scalar_one()
    return count


# ---------------------------------------------------------------------------
# F024 / AC-BEHAV-B05 — upsert-on-first-access
# ---------------------------------------------------------------------------


class TestGetProfileByUserId:
    def test_get_profile_by_user_id_creates_on_first_access(self, db_session: Session) -> None:
        """Calling twice returns the same profile; row count stays at 1."""
        user = _create_user(db_session)

        profile_first = get_profile_by_user_id(db_session, user.id)
        profile_second = get_profile_by_user_id(db_session, user.id)

        assert profile_first.id == profile_second.id
        assert _count_profiles_for(db_session, user.id) == 1

    def test_get_profile_returns_profile_with_correct_user_id(self, db_session: Session) -> None:
        user = _create_user(db_session)
        profile = get_profile_by_user_id(db_session, user.id)

        assert profile.user_id == user.id

    def test_get_profile_initial_completion_is_0(self, db_session: Session) -> None:
        user = _create_user(db_session)
        profile = get_profile_by_user_id(db_session, user.id)

        assert profile.completion_percentage == 0

    def test_get_profile_initial_lists_are_empty(self, db_session: Session) -> None:
        user = _create_user(db_session)
        profile = get_profile_by_user_id(db_session, user.id)

        assert profile.skills == []
        assert profile.education == []
        assert profile.experience == []
        assert profile.certifications == []
        assert profile.projects == []

    def test_different_users_get_separate_profiles(self, db_session: Session) -> None:
        user_a = _create_user(db_session)
        user_b = _create_user(db_session)

        profile_a = get_profile_by_user_id(db_session, user_a.id)
        profile_b = get_profile_by_user_id(db_session, user_b.id)

        assert profile_a.id != profile_b.id
        assert profile_a.user_id == user_a.id
        assert profile_b.user_id == user_b.id


# ---------------------------------------------------------------------------
# F025 / AC-BEHAV-B06 — update_profile persists all 7 sections
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    def test_update_profile_all_sections(self, db_session: Session) -> None:
        """AC-BEHAV-B06: all 7 sections updated; re-fetch returns all."""
        user = _create_user(db_session)

        data = ProfileUpdateData(
            headline="Senior Software Engineer",
            summary="10 years building distributed systems",
            skills=["Python", "Go", "Kubernetes"],
            education=[{"degree": "BSc Computer Science", "school": "MIT"}],
            experience=[{"company": "Acme Corp", "title": "Engineer"}],
            certifications=[{"name": "AWS Solutions Architect"}],
            projects=[{"title": "OpenSource Tool", "url": "https://github.com/x"}],
        )

        updated = update_profile(db_session, user.id, data)

        # Re-fetch from DB to confirm persistence (flush makes it visible in session)
        db_session.expire(db_session.get(ProfileModel, updated.id))  # type: ignore[arg-type]
        re_fetched = get_profile_by_user_id(db_session, user.id)

        assert re_fetched.headline == "Senior Software Engineer"
        assert re_fetched.summary == "10 years building distributed systems"
        assert "Python" in re_fetched.skills
        assert len(re_fetched.education) == 1
        assert re_fetched.education[0]["degree"] == "BSc Computer Science"
        assert len(re_fetched.experience) == 1
        assert re_fetched.experience[0]["company"] == "Acme Corp"
        assert len(re_fetched.certifications) == 1
        assert len(re_fetched.projects) == 1

    def test_update_profile_returns_profile_domain_object(self, db_session: Session) -> None:
        from app.types.domain import Profile

        user = _create_user(db_session)
        result = update_profile(db_session, user.id, ProfileUpdateData(headline="Test"))

        assert isinstance(result, Profile)

    def test_update_profile_does_not_create_duplicate_rows(self, db_session: Session) -> None:
        user = _create_user(db_session)

        # First call creates the profile implicitly
        update_profile(db_session, user.id, ProfileUpdateData(headline="First"))
        # Second call must update in-place
        update_profile(db_session, user.id, ProfileUpdateData(headline="Second"))

        assert _count_profiles_for(db_session, user.id) == 1


# ---------------------------------------------------------------------------
# F026 / AC-SCHEMA-B04 / AC-BEHAV-B07 — completion_percentage recomputation
# ---------------------------------------------------------------------------


class TestCompletionPercentage:
    def test_completion_percentage_full_is_100(self, db_session: Session) -> None:
        """All 7 sections populated → completion_percentage == 100."""
        user = _create_user(db_session)

        data = ProfileUpdateData(
            headline="Engineer",
            summary="Experienced",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[{"name": "AWS"}],
            projects=[{"title": "Demo"}],
        )
        profile = update_profile(db_session, user.id, data)

        assert profile.completion_percentage == 100

    def test_completion_percentage_empty_is_0(self, db_session: Session) -> None:
        """All 7 sections empty → completion_percentage == 0."""
        user = _create_user(db_session)

        data = ProfileUpdateData(
            headline=None,
            summary=None,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        profile = update_profile(db_session, user.id, data)

        assert profile.completion_percentage == 0

    def test_completion_percentage_partial(self, db_session: Session) -> None:
        """3 out of 7 → round(100 * 3/7) == 43."""
        user = _create_user(db_session)

        data = ProfileUpdateData(
            headline="Engineer",
            summary="Text",
            skills=["Python"],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        profile = update_profile(db_session, user.id, data)

        assert profile.completion_percentage == 43

    def test_completion_percentage_recomputed_on_each_update(self, db_session: Session) -> None:
        """Completion changes from 100 → 0 when a second update clears all fields."""
        user = _create_user(db_session)

        # Fill all sections
        full_data = ProfileUpdateData(
            headline="Engineer",
            summary="Experienced",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[{"name": "AWS"}],
            projects=[{"title": "Demo"}],
        )
        profile_full = update_profile(db_session, user.id, full_data)
        assert profile_full.completion_percentage == 100

        # Now clear all sections
        empty_data = ProfileUpdateData()
        profile_empty = update_profile(db_session, user.id, empty_data)
        assert profile_empty.completion_percentage == 0

    def test_completion_percentage_persisted_in_db(self, db_session: Session) -> None:
        """completion_percentage written to DB row — re-fetch confirms value."""
        user = _create_user(db_session)

        data = ProfileUpdateData(
            headline="Engineer",
            summary=None,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
        )
        updated = update_profile(db_session, user.id, data)
        expected_pct = updated.completion_percentage  # 14

        # Expire the ORM row and re-query to force a fresh DB read
        row = db_session.get(ProfileModel, updated.id)
        if row is not None:
            db_session.expire(row)
        re_fetched = get_profile_by_user_id(db_session, user.id)

        assert re_fetched.completion_percentage == expected_pct


# ---------------------------------------------------------------------------
# F027 / AC-BEHAV-B08 — profile isolation
# ---------------------------------------------------------------------------


class TestProfileIsolation:
    def test_profile_isolation(self, db_session: Session) -> None:
        """Updating user A's profile never changes user B's profile."""
        user_a = _create_user(db_session)
        user_b = _create_user(db_session)

        # Establish baseline for both users
        get_profile_by_user_id(db_session, user_a.id)
        profile_b_before = get_profile_by_user_id(db_session, user_b.id)

        # Update user A fully
        data_a = ProfileUpdateData(
            headline="A's headline",
            summary="A's summary",
            skills=["Java"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "A Corp"}],
            certifications=[{"name": "GCP"}],
            projects=[{"title": "Project A"}],
        )
        update_profile(db_session, user_a.id, data_a)

        # Re-fetch user B — should be unchanged
        profile_b_after = get_profile_by_user_id(db_session, user_b.id)

        assert profile_b_after.id == profile_b_before.id
        assert profile_b_after.headline is None
        assert profile_b_after.summary is None
        assert profile_b_after.skills == []
        assert profile_b_after.education == []
        assert profile_b_after.experience == []
        assert profile_b_after.certifications == []
        assert profile_b_after.projects == []
        assert profile_b_after.completion_percentage == 0

    def test_updating_b_does_not_change_a(self, db_session: Session) -> None:
        """Reverse: updating B does not affect A."""
        user_a = _create_user(db_session)
        user_b = _create_user(db_session)

        # Give A a full profile
        data_a = ProfileUpdateData(
            headline="A headline",
            summary="A summary",
            skills=["Python"],
            education=[{"degree": "BSc"}],
            experience=[{"company": "Acme"}],
            certifications=[{"name": "AWS"}],
            projects=[{"title": "MyApp"}],
        )
        profile_a_before = update_profile(db_session, user_a.id, data_a)
        assert profile_a_before.completion_percentage == 100

        # Update B (empty)
        update_profile(db_session, user_b.id, ProfileUpdateData())

        # A unchanged
        profile_a_after = get_profile_by_user_id(db_session, user_a.id)
        assert profile_a_after.headline == "A headline"
        assert profile_a_after.completion_percentage == 100
