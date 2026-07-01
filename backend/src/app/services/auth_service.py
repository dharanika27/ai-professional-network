"""Authentication business logic — register, login, and refresh.

This service orchestrates the security primitives in ``security.py`` and the
repositories in ``app.repositories`` to implement the three auth flows. It is
deliberately HTTP-free (no FastAPI import) and never commits or rolls back the
session — the caller (a FastAPI dependency) owns the transaction lifecycle.

Security properties enforced here:
  - Password minimum length is validated BEFORE any hashing or DB call.
  - Wrong password and unknown email raise the SAME :class:`AuthError` so the
    endpoint cannot be used to enumerate registered accounts.
  - Only the SHA-256 hash of a refresh token is persisted; the raw token is
    returned to the caller and never stored.
  - Refresh tokens are single-use: a successful refresh revokes the presented
    token and records the id of its replacement (``rotated_to``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import RefreshTokenModel
from app.repositories import refresh_token_repository, user_repository
from app.services import security
from app.types.domain import User

# Minimum plaintext password length, validated before hashing.
MIN_PASSWORD_LENGTH = 8


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Generic authentication failure.

    Deliberately identical for unknown email, wrong password, and invalid or
    expired refresh tokens so that callers cannot enumerate accounts or
    distinguish failure causes.
    """

    def __init__(self, message: str = "Invalid credentials.") -> None:
        super().__init__(message)


class PasswordTooShortError(Exception):
    """Raised when a password is shorter than ``MIN_PASSWORD_LENGTH``.

    Raised BEFORE hashing or any database access so that no work is done for a
    trivially invalid password.
    """

    def __init__(self) -> None:
        super().__init__(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class AuthResult(BaseModel):
    """Tokens issued by a successful login or refresh."""

    access_token: str
    refresh_token: str
    user_id: uuid.UUID


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _issue_tokens(session: Session, user_id: uuid.UUID, settings: Settings) -> AuthResult:
    """Create an access token + opaque refresh token and persist the token hash.

    The raw refresh token is returned in the result; only its SHA-256 hash is
    stored. Does not commit — the caller owns the transaction.
    """
    access_token, _jti = security.create_access_token(user_id, settings)
    raw_refresh = security.generate_refresh_token()
    token_hash = security.hash_refresh_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.jwt_refresh_ttl_seconds)

    refresh_token_repository.store_refresh_token(
        session=session,
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    return AuthResult(
        access_token=access_token,
        refresh_token=raw_refresh,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Public flows
# ---------------------------------------------------------------------------


def register(session: Session, email: str, password: str, settings: Settings) -> User:
    """Register a new user.

    Validates the password length before hashing, hashes with Argon2id, and
    persists via the user repository. Does not commit.

    Args:
        session: An injected SQLAlchemy Session (caller owns the transaction).
        email: The user's email address (repository lowercases it).
        password: The plaintext password.
        settings: Application settings carrying the Argon2 parameters.

    Returns:
        The created :class:`User` domain model.

    Raises:
        PasswordTooShortError: If the password is shorter than the minimum.
        DuplicateEmailError: If a user with the email already exists (propagated).
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShortError()

    password_hash = security.hash_password(password, settings)
    return user_repository.create_user(
        session=session,
        email=email,
        password_hash=password_hash,
    )


def login(session: Session, email: str, password: str, settings: Settings) -> AuthResult:
    """Authenticate a user and issue tokens.

    Looks up the user by email and verifies the Argon2 hash. Unknown email and
    wrong password both raise the SAME :class:`AuthError` (no user enumeration).
    On success, issues a JWT access token and an opaque refresh token whose hash
    is stored. Does not commit.

    Args:
        session: An injected SQLAlchemy Session (caller owns the transaction).
        email: The user's email address.
        password: The plaintext password.
        settings: Application settings.

    Returns:
        An :class:`AuthResult` with both tokens.

    Raises:
        AuthError: For unknown email or wrong password (identical error).
    """
    user = user_repository.get_user_by_email(session=session, email=email)
    if user is None or not security.verify_password(password, user.password_hash):
        raise AuthError()

    return _issue_tokens(session, user.id, settings)


def refresh(session: Session, raw_refresh_token: str, settings: Settings) -> AuthResult:
    """Rotate a refresh token and issue a fresh access + refresh token pair.

    Validates the presented token (must exist, not be revoked, not be expired),
    then revokes it and records the id of its replacement in ``rotated_to``.
    Revoked, expired, or unknown tokens raise :class:`AuthError`. Does not commit.

    Args:
        session: An injected SQLAlchemy Session (caller owns the transaction).
        raw_refresh_token: The opaque refresh token presented by the client.
        settings: Application settings.

    Returns:
        An :class:`AuthResult` with the new tokens.

    Raises:
        AuthError: If the token is revoked, expired, or unknown.
    """
    token_hash = security.hash_refresh_token(raw_refresh_token)

    if not refresh_token_repository.is_refresh_token_valid(session=session, token_hash=token_hash):
        raise AuthError()

    # Load the old token row to recover its owner and to record rotation linkage.
    old_row: RefreshTokenModel | None = (
        session.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
    )
    if old_row is None:  # pragma: no cover - guarded by is_refresh_token_valid above
        raise AuthError()

    user_id: uuid.UUID = old_row.user_id
    result = _issue_tokens(session, user_id, settings)

    # Revoke the presented token and link it to its replacement.
    new_hash = security.hash_refresh_token(result.refresh_token)
    new_row: RefreshTokenModel | None = (
        session.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == new_hash).first()
    )
    old_row.revoked = True
    if new_row is not None:  # pragma: no branch - store_refresh_token just flushed it
        old_row.rotated_to = new_row.id

    return result
