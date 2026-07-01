"""Refresh token repository — data access for the refresh_tokens table.

This module owns all read/write operations against the refresh_tokens table.
It never commits, rolls back, or closes the session — the caller (service layer
or FastAPI dependency) is responsible for transaction lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.orm import Session

from app.db.models import RefreshTokenModel
from app.types.domain import RefreshToken

# ---------------------------------------------------------------------------
# Mapping helper
# ---------------------------------------------------------------------------


def _to_refresh_token(row: RefreshTokenModel) -> RefreshToken:
    """Map a RefreshTokenModel ORM row to the RefreshToken domain model.

    Args:
        row: A RefreshTokenModel instance returned by a query.

    Returns:
        A RefreshToken Pydantic domain model with all fields populated.
    """
    return RefreshToken(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        revoked=row.revoked,
        rotated_to=row.rotated_to,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def store_refresh_token(
    session: Session,
    user_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
) -> RefreshToken:
    """Persist a new refresh token record and return the domain model.

    The token is stored with ``revoked=False``. A ``session.flush()`` is called
    so that the database-generated UUID primary key is populated without
    requiring the caller to commit.

    Transaction ownership: the caller is responsible for committing or rolling
    back the session. This function never calls commit/rollback/close.

    Args:
        session: An injected SQLAlchemy Session.
        user_id: The UUID of the owning user.
        token_hash: SHA-256 hex digest of the raw refresh token.
        expires_at: Timezone-aware datetime when the token expires.

    Returns:
        A RefreshToken domain model with the generated UUID id populated.
    """
    row = RefreshTokenModel(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        revoked=False,
    )
    session.add(row)
    session.flush()
    return _to_refresh_token(row)


def revoke_refresh_token(session: Session, token_hash: str) -> None:
    """Mark a refresh token as revoked by setting revoked=True.

    If the token_hash is not found, this is a no-op (no exception raised).

    Transaction ownership: the caller is responsible for committing or rolling
    back the session. This function never calls commit/rollback/close.

    Args:
        session: An injected SQLAlchemy Session.
        token_hash: SHA-256 hex digest of the raw refresh token to revoke.
    """
    row: RefreshTokenModel | None = (
        session.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
    )
    if row is not None:
        row.revoked = True


def is_refresh_token_valid(session: Session, token_hash: str) -> bool:
    """Check whether a refresh token is currently valid.

    A token is valid if and only if all three conditions hold:
    1. A record with the given token_hash exists.
    2. The token has not been revoked (``revoked=False``).
    3. The token has not expired (``expires_at > utcnow``).

    Transaction ownership: read-only query — the caller owns the session.
    This function never calls commit/rollback/close.

    Args:
        session: An injected SQLAlchemy Session.
        token_hash: SHA-256 hex digest of the raw refresh token.

    Returns:
        True if the token exists, is not revoked, and has not expired.
        False for revoked, expired, or unknown tokens.
    """
    now = datetime.now(UTC)
    row: RefreshTokenModel | None = (
        session.query(RefreshTokenModel).filter(RefreshTokenModel.token_hash == token_hash).first()
    )
    if row is None:
        return False
    if row.revoked:
        return False
    # The ORM column is typed as sa.DateTime; cast to runtime datetime for mypy.
    # expires_at may be timezone-naive (stored by DB without tz) — normalise.
    expires_at: datetime = cast(datetime, row.expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > now
