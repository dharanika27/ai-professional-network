"""Integration tests for ResumeRepository against a live PostgreSQL database.

Requires TEST_DATABASE_URL to be set (default: postgresql://app:app@localhost:5433/...).
Uses the db_session fixture from conftest.py (rolls back after each test).

Tests:
  - test_save_resume_success                    — bytes readable back via storage (AC-BEHAV-B10)
  - test_save_resume_mime_rejected_stores_nothing — no resume row in DB (AC-BEHAV-B20)
  - test_save_resume_oversized_stores_nothing     — no resume row in DB (AC-BEHAV-B20)
  - test_delete_resume_removes_file_and_row       — cascade delete of ResumeReview (AC-BEHAV-B11)
  - test_get_resume_by_hash_cache_hit             — same id returned on second lookup (AC-BEHAV-B13)
  - test_get_resume_by_hash_different_user_no_collision — per-user hash isolation (AC-BEHAV-B13)
  - test_storage_key_not_in_web_served_path       — storage dir is tmp_path, not static/ (AC-BEHAV-B12)
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResumeModel, ResumeReviewModel, UserModel
from app.repositories.resume_repository import (
    RESUME_MAX_BYTES,
    FileTooLargeError,
    InvalidMimeTypeError,
    delete_resume,
    get_resume_by_hash,
    save_resume,
)
from app.storage.local_storage import LocalStorage

# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_FAKE_PDF_BYTES = b"%PDF-1.4 fake resume content for testing"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(session: Session) -> UserModel:
    """Create and flush a unique UserModel for test isolation."""
    user = UserModel(
        email=f"resume-test-{uuid.uuid4()}@example.com",
        password_hash="hash",
    )
    session.add(user)
    session.flush()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_save_resume_success(db_session: Session, tmp_path: pytest.fixture) -> None:  # type: ignore[type-arg]
    """Bytes are readable back from storage after save_resume (AC-BEHAV-B10)."""
    user = _make_user(db_session)
    storage = LocalStorage(tmp_path / "resumes")

    resume_id = save_resume(
        session=db_session,
        storage=storage,
        user_id=user.id,
        file_bytes=_FAKE_PDF_BYTES,
        original_filename="resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_FAKE_PDF_BYTES),
    )

    # Verify DB row exists
    row = db_session.scalars(select(ResumeModel).where(ResumeModel.id == resume_id)).first()
    assert row is not None, "ResumeModel row should be present after save_resume"
    assert row.user_id == user.id
    assert row.mime_type == _PDF_MIME
    assert row.original_filename == "resume.pdf"

    # Verify bytes readable back from storage
    stored_bytes = storage.read(row.storage_key)
    assert stored_bytes == _FAKE_PDF_BYTES


def test_save_resume_mime_rejected_stores_nothing(
    db_session: Session,
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """Invalid MIME type → InvalidMimeTypeError, no DB row created (AC-BEHAV-B20)."""
    user = _make_user(db_session)
    storage = LocalStorage(tmp_path / "resumes")

    with pytest.raises(InvalidMimeTypeError):
        save_resume(
            session=db_session,
            storage=storage,
            user_id=user.id,
            file_bytes=_FAKE_PDF_BYTES,
            original_filename="resume.exe",
            mime_type="application/octet-stream",
            size_bytes=len(_FAKE_PDF_BYTES),
        )

    # Verify no resume row exists for this user
    rows = db_session.scalars(select(ResumeModel).where(ResumeModel.user_id == user.id)).all()
    assert rows == [], "No ResumeModel row should exist after MIME rejection"


def test_save_resume_oversized_stores_nothing(
    db_session: Session,
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """Oversized file → FileTooLargeError, no DB row created (AC-BEHAV-B20)."""
    user = _make_user(db_session)
    storage = LocalStorage(tmp_path / "resumes")

    with pytest.raises(FileTooLargeError):
        save_resume(
            session=db_session,
            storage=storage,
            user_id=user.id,
            file_bytes=_FAKE_PDF_BYTES,
            original_filename="huge.pdf",
            mime_type=_PDF_MIME,
            size_bytes=RESUME_MAX_BYTES + 1,
        )

    rows = db_session.scalars(select(ResumeModel).where(ResumeModel.user_id == user.id)).all()
    assert rows == [], "No ResumeModel row should exist after size rejection"


def test_delete_resume_removes_file_and_row(
    db_session: Session,
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """delete_resume removes the file from storage and cascades to ResumeReview rows (AC-BEHAV-B11)."""
    user = _make_user(db_session)
    storage = LocalStorage(tmp_path / "resumes")

    resume_id = save_resume(
        session=db_session,
        storage=storage,
        user_id=user.id,
        file_bytes=_FAKE_PDF_BYTES,
        original_filename="resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_FAKE_PDF_BYTES),
    )

    # Fetch storage_key and file_hash before deletion
    row = db_session.scalars(select(ResumeModel).where(ResumeModel.id == resume_id)).first()
    assert row is not None
    storage_key = row.storage_key
    file_hash = row.file_hash

    # Add a ResumeReview to verify cascade
    review = ResumeReviewModel(
        resume_id=resume_id,
        user_id=user.id,
        resume_file_hash=file_hash,
        status="completed",
    )
    db_session.add(review)
    db_session.flush()
    review_id = review.id

    # Delete the resume
    delete_resume(
        session=db_session,
        storage=storage,
        resume_id=resume_id,
        user_id=user.id,
    )

    # Verify DB row is gone
    deleted_row = db_session.scalars(select(ResumeModel).where(ResumeModel.id == resume_id)).first()
    assert deleted_row is None, "ResumeModel row should be deleted"

    # Verify cascade deleted the review
    deleted_review = db_session.scalars(
        select(ResumeReviewModel).where(ResumeReviewModel.id == review_id)
    ).first()
    assert deleted_review is None, "ResumeReviewModel row should be cascade-deleted"

    # Verify file is removed from storage
    import pytest as _pytest

    with _pytest.raises(FileNotFoundError):
        storage.read(storage_key)


def test_get_resume_by_hash_cache_hit(
    db_session: Session,
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """get_resume_by_hash returns the same id as was saved (AC-BEHAV-B13)."""
    user = _make_user(db_session)
    storage = LocalStorage(tmp_path / "resumes")

    resume_id = save_resume(
        session=db_session,
        storage=storage,
        user_id=user.id,
        file_bytes=_FAKE_PDF_BYTES,
        original_filename="resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_FAKE_PDF_BYTES),
    )

    expected_hash = hashlib.sha256(_FAKE_PDF_BYTES).hexdigest()
    found = get_resume_by_hash(db_session, user.id, expected_hash)

    assert found is not None, "get_resume_by_hash should find the saved resume"
    assert found.id == resume_id


def test_get_resume_by_hash_different_user_no_collision(
    db_session: Session,
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """Two users uploading identical bytes produce distinct records (AC-BEHAV-B13)."""
    user_a = _make_user(db_session)
    user_b = _make_user(db_session)
    storage = LocalStorage(tmp_path / "resumes")

    id_a = save_resume(
        session=db_session,
        storage=storage,
        user_id=user_a.id,
        file_bytes=_FAKE_PDF_BYTES,
        original_filename="resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_FAKE_PDF_BYTES),
    )
    id_b = save_resume(
        session=db_session,
        storage=storage,
        user_id=user_b.id,
        file_bytes=_FAKE_PDF_BYTES,
        original_filename="resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_FAKE_PDF_BYTES),
    )

    assert id_a != id_b, "Two users uploading the same bytes must get distinct resume IDs"

    file_hash = hashlib.sha256(_FAKE_PDF_BYTES).hexdigest()

    found_a = get_resume_by_hash(db_session, user_a.id, file_hash)
    found_b = get_resume_by_hash(db_session, user_b.id, file_hash)

    assert found_a is not None and found_b is not None
    assert found_a.id == id_a
    assert found_b.id == id_b

    # Cross-user isolation: user_a's hash lookup should not return user_b's record
    assert found_a.id != found_b.id


def test_storage_key_not_in_web_served_path(
    db_session: Session,
    tmp_path: pytest.fixture,  # type: ignore[type-arg]
) -> None:
    """storage_dir is tmp_path (not under static/), so keys are never web-accessible (AC-BEHAV-B12)."""
    # tmp_path is guaranteed to be outside any static/ directory
    storage_dir = tmp_path / "private_uploads"
    storage = LocalStorage(storage_dir)
    user = _make_user(db_session)

    resume_id = save_resume(
        session=db_session,
        storage=storage,
        user_id=user.id,
        file_bytes=_FAKE_PDF_BYTES,
        original_filename="resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_FAKE_PDF_BYTES),
    )

    row = db_session.scalars(select(ResumeModel).where(ResumeModel.id == resume_id)).first()
    assert row is not None

    # The storage dir must NOT contain "static" in its path
    assert "static" not in str(storage_dir), (
        "Storage directory must not be under a web-served static path"
    )

    # The storage_key must be UUID-format (opaque), not a filename
    import re

    uuid4_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    assert uuid4_re.match(row.storage_key), (
        f"storage_key '{row.storage_key}' must be UUID4-formatted (opaque)"
    )
