"""User repository — data access for the users table.

This module owns all read/write operations against the users table.
It never commits, rolls back, or closes the session — the caller (service layer
or FastAPI dependency) is responsible for transaction lifecycle.
"""

from __future__ import annotations

import uuid

import sqlalchemy.exc
from sqlalchemy.orm import Session

from app.db.models import UserModel
from app.types.domain import User
from app.types.enums import ThemePreference

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class DuplicateEmailError(Exception):
    """Raised when create_user is called with an email that already exists.

    This is a typed alternative to propagating the raw sqlalchemy IntegrityError
    so callers can handle it without depending on SQLAlchemy internals.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"A user with email '{email}' already exists.")
        self.email = email


# ---------------------------------------------------------------------------
# Mapping helper
# ---------------------------------------------------------------------------


def _to_user(row: UserModel) -> User:
    """Map a UserModel ORM row to the User domain model.

    Args:
        row: A UserModel instance returned by a query.

    Returns:
        A User Pydantic domain model with all fields populated.
    """
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        theme_preference=ThemePreference(row.theme_preference),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def create_user(session: Session, email: str, password_hash: str) -> User:
    """Persist a new user to the database and return the domain model.

    The email is lowercased before storage. A ``session.flush()`` is called
    after ``session.add()`` so that the database-generated UUID primary key is
    populated without requiring the caller to commit.

    Transaction ownership: the caller is responsible for committing or rolling
    back the session. This function never calls commit/rollback/close.

    Args:
        session: An injected SQLAlchemy Session.
        email: The user's email address (will be lower-cased).
        password_hash: Pre-hashed password string (Argon2id expected).

    Returns:
        A User domain model with the generated UUID id populated.

    Raises:
        DuplicateEmailError: If a user with the same (lowercased) email exists.
        sqlalchemy.exc.IntegrityError: For any other integrity constraint violation.
    """
    normalized_email = email.lower()
    row = UserModel(
        email=normalized_email,
        password_hash=password_hash,
    )
    session.add(row)
    try:
        session.flush()
    except sqlalchemy.exc.IntegrityError as exc:
        # Detect unique-constraint violations on the email column.
        # The error message from psycopg/PostgreSQL includes the column name.
        error_text = str(exc).lower()
        if "email" in error_text or "users_email" in error_text or "uq_users" in error_text:
            raise DuplicateEmailError(normalized_email) from exc
        raise

    return _to_user(row)


def get_user_by_email(session: Session, email: str) -> User | None:
    """Look up a user by email address (case-insensitive).

    Emails are stored lower-cased; the incoming email is lowercased before
    querying so lookups are always case-insensitive.

    Transaction ownership: read-only query — the caller owns the session.
    This function never calls commit/rollback/close.

    Args:
        session: An injected SQLAlchemy Session.
        email: Email address to search for (case-insensitive).

    Returns:
        A User domain model if found, or None if no matching user exists.
    """
    normalized_email = email.lower()
    row: UserModel | None = (
        session.query(UserModel).filter(UserModel.email == normalized_email).first()
    )
    if row is None:
        return None
    return _to_user(row)


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    """Look up a user by their UUID primary key.

    Transaction ownership: read-only query — the caller owns the session.
    This function never calls commit/rollback/close.

    Args:
        session: An injected SQLAlchemy Session.
        user_id: The UUID primary key of the user.

    Returns:
        A User domain model if found, or None.
    """
    row: UserModel | None = session.query(UserModel).filter(UserModel.id == user_id).first()
    if row is None:
        return None
    return _to_user(row)
