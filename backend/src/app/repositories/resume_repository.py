"""Resume repository — data-models.md §2.4, E4-S1.

Provides:
  - save_resume   — validate, store file bytes, persist metadata; returns resume UUID
  - delete_resume — remove stored file + metadata row (ResumeReview cascade via FK)
  - get_resume_by_hash — cache-hit lookup by (user_id, file_hash)
  - get_resume_by_id   — lookup by primary key

CRITICAL:
  - Never call session.commit(), session.rollback(), or session.close().
  - Never import LocalStorage here — depend on the StorageBackend Protocol only.
  - storage_key is OPAQUE (uuid4-based); never derived from user input.
  - original_filename is SANITIZED before persistence.
  - REJECT invalid MIME / oversized file BEFORE any DB or storage write.
"""

from __future__ import annotations

import hashlib
import pathlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResumeModel
from app.storage.base import StorageBackend
from app.types.domain import Resume
from app.types.enums import MimeType, ParseStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
RESUME_MAX_BYTES: int = 5_242_880  # 5 MiB


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class InvalidMimeTypeError(Exception):
    """Raised when the uploaded file has a MIME type not in ALLOWED_MIME_TYPES."""


class FileTooLargeError(Exception):
    """Raised when the uploaded file exceeds RESUME_MAX_BYTES."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sanitize_filename(original_filename: str) -> str:
    """Strip path components and truncate to 255 chars.

    pathlib.Path(name).name extracts only the final component,
    preventing directory traversal via crafted filenames.
    """
    name = pathlib.Path(original_filename).name
    return name[:255]


def _to_resume(row: ResumeModel) -> Resume:
    """Map a ResumeModel ORM row to the Resume domain object."""
    return Resume(
        id=row.id,
        user_id=row.user_id,
        original_filename=row.original_filename,
        mime_type=MimeType(row.mime_type),
        size_bytes=row.size_bytes,
        file_hash=row.file_hash,
        storage_key=row.storage_key,
        parse_status=ParseStatus(row.parse_status),
        structured_content=None,  # parsing is a separate epic
        embedding=None,
        parse_error=row.parse_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


def save_resume(
    session: Session,
    storage: StorageBackend,
    user_id: uuid.UUID,
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
) -> uuid.UUID:
    """Validate, store file bytes, persist metadata. Returns resume id.

    REJECTS (raises typed error, stores NOTHING) if:
    - mime_type not in ALLOWED_MIME_TYPES → InvalidMimeTypeError
    - size_bytes > RESUME_MAX_BYTES       → FileTooLargeError

    Transaction boundary: caller owns commit/rollback.
    Storage key is opaque server-generated (uuid-based), NEVER derived from user input.
    original_filename is sanitized (path components stripped, ≤255 chars).
    """
    # --- Validate BEFORE any write ---
    if mime_type not in ALLOWED_MIME_TYPES:
        raise InvalidMimeTypeError(
            f"MIME type '{mime_type}' is not allowed. Allowed types: {sorted(ALLOWED_MIME_TYPES)}"
        )

    if size_bytes > RESUME_MAX_BYTES:
        raise FileTooLargeError(
            f"File size {size_bytes} bytes exceeds maximum of {RESUME_MAX_BYTES} bytes."
        )

    # --- Sanitize filename ---
    safe_filename = _sanitize_filename(original_filename)

    # --- Compute file hash ---
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # --- Generate opaque storage key (NOT derived from filename) ---
    storage_key = str(uuid.uuid4())

    # --- Persist file bytes to storage ---
    storage.save(storage_key, file_bytes)

    # --- Persist metadata to DB ---
    row = ResumeModel(
        user_id=user_id,
        original_filename=safe_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        file_hash=file_hash,
        storage_key=storage_key,
        parse_status=ParseStatus.PENDING,
    )
    session.add(row)
    session.flush()  # assigns row.id, created_at, updated_at from DB

    return row.id


def delete_resume(
    session: Session,
    storage: StorageBackend,
    resume_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete stored file + metadata row. ResumeReview rows cascade via FK.

    Storage file removed BEFORE DB row (sequenced for consistency).
    If resume not found for (resume_id, user_id): no-op.
    Transaction boundary: caller owns commit/rollback.
    """
    stmt = select(ResumeModel).where(
        ResumeModel.id == resume_id,
        ResumeModel.user_id == user_id,
    )
    row = session.scalars(stmt).first()

    if row is None:
        return

    # Remove from storage first; if this fails, DB row is untouched
    storage.delete(row.storage_key)

    # Remove the ORM row (FK cascade deletes ResumeReview rows)
    session.delete(row)
    session.flush()


def get_resume_by_hash(
    session: Session,
    user_id: uuid.UUID,
    file_hash: str,
) -> Resume | None:
    """Return existing resume for (user_id, file_hash) or None (cache hit logic).

    AC-BEHAV-B13: hash-based deduplication scoped per user.
    """
    stmt = select(ResumeModel).where(
        ResumeModel.user_id == user_id,
        ResumeModel.file_hash == file_hash,
    )
    row = session.scalars(stmt).first()
    return _to_resume(row) if row is not None else None


def get_resume_by_id(
    session: Session,
    resume_id: uuid.UUID,
) -> Resume | None:
    """Return resume by id or None."""
    stmt = select(ResumeModel).where(ResumeModel.id == resume_id)
    row = session.scalars(stmt).first()
    return _to_resume(row) if row is not None else None
