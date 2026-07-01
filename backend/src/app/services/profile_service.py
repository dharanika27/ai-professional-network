"""Profile service — view, edit, completion, and skill normalization (E3-S2).

Provides HTTP-free profile operations on top of profile_repository:
  - get_profile     — ownership-checked read; returns profile + incomplete sections
  - update_profile  — validate constraints, normalize skills, persist

CRITICAL boundaries (CLAUDE.md / architecture.md):
  - No fastapi import — services are transport-agnostic.
  - No session.commit()/rollback()/close() — the caller owns the transaction.
  - A user may only read/edit their OWN profile; mismatch → ProfileAuthorizationError.

Skill normalization (AC-BEHAV-C20): strip whitespace, drop empties, deduplicate
preserving the first occurrence and preserving case ('Python' != 'python').
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.repositories import profile_repository
from app.repositories.profile_repository import ProfileUpdateData
from app.types.domain import Profile

# ---------------------------------------------------------------------------
# Field constraints (mirror data-models.md §2.3)
# ---------------------------------------------------------------------------

_MAX_FULL_NAME = 120
_MAX_HEADLINE = 160
_MAX_SUMMARY = 2000

# The 7 equally-weighted completion sections, in canonical order.
_SECTION_NAMES = (
    "headline",
    "summary",
    "skills",
    "education",
    "experience",
    "certifications",
    "projects",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProfileAuthorizationError(Exception):
    """Raised when a user tries to access another user's profile."""


class ProfileValidationError(Exception):
    """Raised when profile field constraints are violated."""


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ProfileUpdateRequest:
    """Input for profile updates — all fields optional.

    For each field, ``None`` means "leave unchanged". For the list fields an
    explicit ``[]`` means "clear", except ``skills`` which rejects an empty
    list (see update_profile).
    """

    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] | None = None
    education: list[dict[str, Any]] | None = None
    experience: list[dict[str, Any]] | None = None
    certifications: list[dict[str, Any]] | None = None
    projects: list[dict[str, Any]] | None = None


@dataclass
class ProfileDTO:
    """Safe profile data including completion info."""

    profile: Profile
    incomplete_sections: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_ownership(requesting_user_id: uuid.UUID, profile_owner_id: uuid.UUID) -> None:
    """Raise ProfileAuthorizationError unless the requester owns the profile."""
    if requesting_user_id != profile_owner_id:
        raise ProfileAuthorizationError("requesting user may only access their own profile")


def _incomplete_sections(profile: Profile) -> list[str]:
    """Return the canonical list of empty section names for *profile*.

    headline/summary count as empty when None or the empty string; the five
    list sections count as empty when they contain no elements.
    """
    populated: dict[str, bool] = {
        "headline": bool(profile.headline),
        "summary": bool(profile.summary),
        "skills": len(profile.skills) > 0,
        "education": len(profile.education) > 0,
        "experience": len(profile.experience) > 0,
        "certifications": len(profile.certifications) > 0,
        "projects": len(profile.projects) > 0,
    }
    return [name for name in _SECTION_NAMES if not populated[name]]


def _normalize_skills(skills: list[str]) -> list[str]:
    """Strip, drop empties, and deduplicate skills (case-preserved, order-stable).

    AC-BEHAV-C20: 'Python' and ' Python ' collapse to one 'Python', but
    'python' remains distinct from 'Python'.
    """
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in skills:
        stripped = raw.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        normalized.append(stripped)
    return normalized


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_profile(
    session: Session,
    requesting_user_id: uuid.UUID,
    profile_owner_id: uuid.UUID,
) -> ProfileDTO:
    """Return the owner's profile with completion info.

    Raises ProfileAuthorizationError if the requester is not the owner.
    Delegates to the repository, which creates a blank profile on first access.
    """
    _require_ownership(requesting_user_id, profile_owner_id)

    profile = profile_repository.get_profile_by_user_id(session, profile_owner_id)
    return ProfileDTO(
        profile=profile,
        incomplete_sections=_incomplete_sections(profile),
    )


def update_profile(
    session: Session,
    requesting_user_id: uuid.UUID,
    profile_owner_id: uuid.UUID,
    data: ProfileUpdateRequest,
    settings: Settings,
) -> ProfileDTO:
    """Validate, normalize, and persist a profile update.

    Ownership is checked first, then field constraints are validated BEFORE any
    repository call so an invalid request never touches the database. Skills are
    normalized per AC-BEHAV-C20. ``settings`` is accepted for signature
    consistency with sibling services but is unused here.
    """
    del settings  # unused; kept for cross-service signature consistency

    _require_ownership(requesting_user_id, profile_owner_id)

    if data.full_name is not None and len(data.full_name) > _MAX_FULL_NAME:
        raise ProfileValidationError(f"full_name exceeds {_MAX_FULL_NAME} characters")
    if data.headline is not None and len(data.headline) > _MAX_HEADLINE:
        raise ProfileValidationError(f"headline exceeds {_MAX_HEADLINE} characters")
    if data.summary is not None and len(data.summary) > _MAX_SUMMARY:
        raise ProfileValidationError(f"summary exceeds {_MAX_SUMMARY} characters")

    normalized_skills: list[str] | None = None
    if data.skills is not None:
        if len(data.skills) == 0:
            raise ProfileValidationError("skills must not be an empty list")
        normalized_skills = _normalize_skills(data.skills)
        if not normalized_skills:
            raise ProfileValidationError("skills must contain at least one non-empty value")

    update = ProfileUpdateData(
        headline=data.headline,
        summary=data.summary,
        skills=normalized_skills if normalized_skills is not None else [],
        education=data.education if data.education is not None else [],
        experience=data.experience if data.experience is not None else [],
        certifications=data.certifications if data.certifications is not None else [],
        projects=data.projects if data.projects is not None else [],
    )

    profile = profile_repository.update_profile(session, profile_owner_id, update)
    return ProfileDTO(
        profile=profile,
        incomplete_sections=_incomplete_sections(profile),
    )
