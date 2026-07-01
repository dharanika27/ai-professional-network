"""Unit tests for ResumeRepository functions (pure logic, no DB).

Uses an in-memory stub for StorageBackend and a mock Session so no database
connection is required.

Tests:
  - test_save_resume_rejects_invalid_mime  — InvalidMimeTypeError, no writes
  - test_save_resume_rejects_oversized     — FileTooLargeError, no writes
  - test_storage_key_is_opaque_not_filename — storage_key is UUID-format, not filename
  - test_filename_sanitization             — "../../evil.pdf" → "evil.pdf"
"""

from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.repositories.resume_repository import (
    RESUME_MAX_BYTES,
    FileTooLargeError,
    InvalidMimeTypeError,
    _sanitize_filename,
    save_resume,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_INVALID_MIME = "text/plain"
_SMALL_BYTES = b"%PDF-1.4 tiny resume"
_USER_ID = uuid.uuid4()

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class _InMemoryStorage:
    """Minimal in-memory StorageBackend stub for unit tests."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self.saved_keys: list[str] = []

    def save(self, key: str, data: bytes) -> None:
        self._store[key] = data
        self.saved_keys.append(key)

    def read(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


def _make_session() -> Any:
    """Return a MagicMock that mimics a minimal SQLAlchemy Session."""
    session = MagicMock()
    # flush() should succeed without side-effects
    session.flush.return_value = None
    # Model add tracking
    session.add.return_value = None
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_save_resume_rejects_invalid_mime() -> None:
    """MIME type not in ALLOWED_MIME_TYPES → InvalidMimeTypeError before any write."""
    session = _make_session()
    storage = _InMemoryStorage()

    with pytest.raises(InvalidMimeTypeError):
        save_resume(
            session=session,
            storage=storage,
            user_id=_USER_ID,
            file_bytes=_SMALL_BYTES,
            original_filename="resume.txt",
            mime_type=_INVALID_MIME,
            size_bytes=len(_SMALL_BYTES),
        )

    # Nothing should be stored or added to DB
    assert storage.saved_keys == [], "No file should be written on MIME rejection"
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_save_resume_rejects_oversized() -> None:
    """size_bytes > RESUME_MAX_BYTES → FileTooLargeError before any write."""
    session = _make_session()
    storage = _InMemoryStorage()
    oversized = RESUME_MAX_BYTES + 1

    with pytest.raises(FileTooLargeError):
        save_resume(
            session=session,
            storage=storage,
            user_id=_USER_ID,
            file_bytes=_SMALL_BYTES,  # actual bytes irrelevant; size_bytes drives check
            original_filename="resume.pdf",
            mime_type=_PDF_MIME,
            size_bytes=oversized,
        )

    assert storage.saved_keys == [], "No file should be written on size rejection"
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_storage_key_is_opaque_not_filename() -> None:
    """storage_key must be a UUID4, never derived from original_filename.

    AC-BEHAV-B12: opaque server-generated key.
    """
    session = _make_session()
    storage = _InMemoryStorage()

    # Capture what key was used to save
    saved_calls: list[str] = []
    original_save = storage.save

    def tracking_save(key: str, data: bytes) -> None:
        saved_calls.append(key)
        original_save(key, data)

    storage.save = tracking_save  # type: ignore[method-assign]

    save_resume(
        session=session,
        storage=storage,
        user_id=_USER_ID,
        file_bytes=_SMALL_BYTES,
        original_filename="my-resume.pdf",
        mime_type=_PDF_MIME,
        size_bytes=len(_SMALL_BYTES),
    )

    assert len(saved_calls) == 1, "Exactly one storage.save call expected"
    used_key = saved_calls[0]

    assert _UUID4_RE.match(used_key), f"storage_key '{used_key}' is not a valid UUID4 pattern"
    assert "my-resume" not in used_key, (
        "storage_key must not contain any part of the original filename"
    )
    assert "my_resume" not in used_key


def test_filename_sanitization() -> None:
    """Path traversal in filename is stripped to base filename only."""
    result = _sanitize_filename("../../evil.pdf")
    assert result == "evil.pdf", f"Expected 'evil.pdf' after sanitization, got '{result}'"


def test_filename_sanitization_long_name() -> None:
    """Filenames longer than 255 chars are truncated."""
    long_name = "a" * 300 + ".pdf"
    result = _sanitize_filename(long_name)
    assert len(result) <= 255


# ---------------------------------------------------------------------------
# delete_resume — when row does not exist (covers resume_repository.py line 173)
# ---------------------------------------------------------------------------


def test_delete_resume_noop_when_row_not_found() -> None:
    """delete_resume must silently do nothing if no matching row is found.

    Covers the early-return path at resume_repository.py line 173.
    """
    from app.repositories.resume_repository import delete_resume

    session = MagicMock()
    session.scalars.return_value.first.return_value = None  # no row found

    storage = _InMemoryStorage()
    user_id = uuid.uuid4()
    nonexistent_id = uuid.uuid4()

    # Must not raise and must not call storage.delete or session.delete
    delete_resume(session, storage, nonexistent_id, user_id)

    assert storage.saved_keys == [], "No file should be deleted when row is missing"
    session.delete.assert_not_called()
    session.flush.assert_not_called()


# ---------------------------------------------------------------------------
# get_resume_by_id — covers resume_repository.py lines 205-207
# ---------------------------------------------------------------------------


def test_get_resume_by_id_returns_none_when_not_found() -> None:
    """get_resume_by_id must return None when no row matches the given id.

    Covers resume_repository.py lines 205-207.
    """
    from app.repositories.resume_repository import get_resume_by_id

    session = MagicMock()
    session.scalars.return_value.first.return_value = None

    result = get_resume_by_id(session, uuid.uuid4())
    assert result is None


def test_get_resume_by_id_returns_resume_when_found() -> None:
    """get_resume_by_id must return a Resume when the row exists."""
    import uuid as _uuid
    from datetime import UTC, datetime

    from app.repositories.resume_repository import get_resume_by_id
    from app.types.domain import Resume
    from app.types.enums import MimeType, ParseStatus

    session = MagicMock()
    resume_id = _uuid.uuid4()
    user_id = _uuid.uuid4()

    row = MagicMock()
    row.id = resume_id
    row.user_id = user_id
    row.original_filename = "test.pdf"
    row.storage_key = str(_uuid.uuid4())
    row.mime_type = MimeType.PDF.value
    row.size_bytes = 1024
    row.file_hash = "abc123"
    row.parse_status = ParseStatus.PENDING.value
    row.structured_content = None
    row.embedding = None
    row.parse_error = None
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)

    session.scalars.return_value.first.return_value = row

    result = get_resume_by_id(session, resume_id)

    assert result is not None
    assert isinstance(result, Resume)
    assert result.id == resume_id


def test_filename_sanitization_windows_path() -> None:
    """Windows-style path separators in filename are also stripped."""
    result = _sanitize_filename(r"C:\Users\attacker\evil.pdf")
    # pathlib.Path(...).name handles backslash on all platforms
    assert "\\" not in result
    assert "attacker" not in result
