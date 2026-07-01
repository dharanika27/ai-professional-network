"""Profile repository — data-models.md §2.3, F024/F025/F026/F027.

Provides:
  - get_profile_by_user_id  — upsert-on-first-access, returns Profile or None
  - update_profile          — atomic field update + completion recompute
  - compute_completion_percentage — pure function, exported for unit tests

CRITICAL: never call session.commit(), session.rollback(), or session.close().
Use session.flush() after add/update so the caller (service / FastAPI dep) owns
the transaction boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProfileModel
from app.types.domain import Profile

# ---------------------------------------------------------------------------
# Data-transfer object for updates
# ---------------------------------------------------------------------------


@dataclass
class ProfileUpdateData:
    """Typed container for profile field updates (F025)."""

    headline: str | None = None
    summary: str | None = None
    skills: list[str] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    experience: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Completion percentage algorithm  (data-models.md §2.3, F026/AC-SCHEMA-B04)
# ---------------------------------------------------------------------------

_TOTAL_SECTIONS = 7


def compute_completion_percentage(
    headline: str | None,
    summary: str | None,
    skills: list[Any],
    education: list[Any],
    experience: list[Any],
    certifications: list[Any],
    projects: list[Any],
) -> int:
    """Return completion_percentage for the 7 equally-weighted sections.

    Formula: round(100 * populated_count / 7)

    Section rules:
        - headline / summary: populated if non-None AND non-empty string
        - skills / education / experience / certifications / projects:
          populated if the list has at least one element
    """
    populated = sum(
        [
            bool(headline),  # non-None and non-empty str → truthy
            bool(summary),
            len(skills) > 0,
            len(education) > 0,
            len(experience) > 0,
            len(certifications) > 0,
            len(projects) > 0,
        ]
    )
    return round(100 * populated / _TOTAL_SECTIONS)


# ---------------------------------------------------------------------------
# ORM → domain mapper
# ---------------------------------------------------------------------------


def _to_profile(row: ProfileModel) -> Profile:
    """Map a ProfileModel ORM row to the Profile domain object."""
    return Profile(
        id=row.id,
        user_id=row.user_id,
        full_name=row.full_name,
        headline=row.headline,
        summary=row.summary,
        skills=list(row.skills) if row.skills else [],
        education=list(row.education) if row.education else [],
        experience=list(row.experience) if row.experience else [],
        certifications=list(row.certifications) if row.certifications else [],
        projects=list(row.projects) if row.projects else [],
        completion_percentage=row.completion_percentage,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


def get_profile_by_user_id(session: Session, user_id: uuid.UUID) -> Profile:
    """Return the Profile for *user_id*, creating a blank one on first access.

    AC-BEHAV-B05 (F024): upsert-on-first-access semantics.
    A UNIQUE constraint on user_id prevents duplicates.
    """
    stmt = select(ProfileModel).where(ProfileModel.user_id == user_id)
    row = session.scalars(stmt).first()

    if row is None:
        row = ProfileModel(
            user_id=user_id,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
            completion_percentage=0,
        )
        session.add(row)
        session.flush()  # assigns row.id, created_at, updated_at from DB

    return _to_profile(row)


def update_profile(
    session: Session,
    user_id: uuid.UUID,
    data: ProfileUpdateData,
) -> Profile:
    """Atomically persist profile fields and recompute completion_percentage.

    AC-BEHAV-B06 (F025): all 7 sections written atomically.
    AC-BEHAV-B07 / AC-SCHEMA-B04 (F026): completion recalculated every call.
    AC-BEHAV-B08 (F027): scoped to user_id — never touches another user's row.
    """
    stmt = select(ProfileModel).where(ProfileModel.user_id == user_id)
    row = session.scalars(stmt).first()

    if row is None:
        row = ProfileModel(
            user_id=user_id,
            skills=[],
            education=[],
            experience=[],
            certifications=[],
            projects=[],
            completion_percentage=0,
        )
        session.add(row)

    # Apply all fields
    # NOTE: ProfileModel declares JSONB columns as dict[str, Any] but they store
    # lists at runtime.  The type: ignore[assignment] suppresses the mismatch
    # that mypy cannot resolve without changing the shared ORM model.
    row.headline = data.headline
    row.summary = data.summary
    row.skills = list(data.skills)  # type: ignore[assignment]
    row.education = list(data.education)  # type: ignore[assignment]
    row.experience = list(data.experience)  # type: ignore[assignment]
    row.certifications = list(data.certifications)  # type: ignore[assignment]
    row.projects = list(data.projects)  # type: ignore[assignment]

    # Recompute completion_percentage
    row.completion_percentage = compute_completion_percentage(
        headline=row.headline,
        summary=row.summary,
        skills=list(row.skills),
        education=list(row.education),
        experience=list(row.experience),
        certifications=list(row.certifications),
        projects=list(row.projects),
    )

    session.flush()
    return _to_profile(row)
