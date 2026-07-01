"""Security primitives — password hashing and JWT/refresh-token helpers.

This module is deliberately HTTP-free and provider-agnostic so that alternative
auth strategies (e.g. Google OAuth) can be dropped in later without touching the
business logic in ``auth_service.py``.

Responsibilities:
  - Argon2id password hashing + timing-safe verification
  - HS256 JWT access-token creation and verification
  - Opaque refresh-token generation + SHA-256 hashing for storage

Never imports FastAPI. Never touches the database or a Session.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jose import jwt

from app.config.settings import Settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"

# Number of random bytes for opaque refresh tokens. 32 bytes -> ~43 url-safe chars.
_REFRESH_TOKEN_BYTES = 32


# ---------------------------------------------------------------------------
# Password hashing (Argon2id)
# ---------------------------------------------------------------------------


def _build_hasher(settings: Settings) -> PasswordHasher:
    """Construct an Argon2id PasswordHasher from the configured cost parameters."""
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_kib,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(password: str, settings: Settings) -> str:
    """Hash a password with Argon2id using the configured cost parameters.

    Args:
        password: The plaintext password to hash.
        settings: Application settings carrying the Argon2 cost parameters.

    Returns:
        An encoded Argon2id hash string beginning with ``$argon2id$``.
    """
    return _build_hasher(settings).hash(password)


def verify_password(password: str, hash: str) -> bool:
    """Verify a plaintext password against an Argon2 hash in a timing-safe way.

    A fresh :class:`PasswordHasher` is used for verification; the cost
    parameters are embedded in the encoded hash string, so no settings are
    required here.

    Args:
        password: The plaintext password to check.
        hash: A previously produced Argon2 encoded hash string.

    Returns:
        True on a match, False on a mismatch or malformed hash.
    """
    try:
        return PasswordHasher().verify(hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------------------
# JWT access tokens (HS256)
# ---------------------------------------------------------------------------


def create_access_token(user_id: uuid.UUID, settings: Settings) -> tuple[str, str]:
    """Create a signed HS256 JWT access token.

    The payload contains ``sub`` (string UUID), ``iat``, ``exp`` and ``jti``
    (a fresh uuid4). The lifetime honours ``settings.jwt_access_ttl_seconds``.

    Args:
        user_id: The subject user's UUID.
        settings: Application settings carrying the signing secret and TTL.

    Returns:
        A tuple of ``(token_str, jti)`` where ``jti`` is the token's unique id.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(seconds=settings.jwt_access_ttl_seconds)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, jti


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify and decode an HS256 JWT access token.

    Args:
        token: The encoded JWT string.
        settings: Application settings carrying the signing secret.

    Returns:
        The decoded claims dictionary.

    Raises:
        jose.JWTError: If the signature is invalid or the token has expired.
    """
    claims: dict[str, Any] = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    return claims


# ---------------------------------------------------------------------------
# Opaque refresh tokens
# ---------------------------------------------------------------------------


def generate_refresh_token() -> str:
    """Generate a cryptographically random, opaque refresh token.

    The token is high-entropy random text (not a JWT). Only its SHA-256 hash
    is ever persisted; the raw token is returned to the caller exactly once.

    Returns:
        A url-safe random string.
    """
    return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw refresh token for storage.

    Args:
        raw_token: The opaque refresh token string.

    Returns:
        A 64-character lowercase hex SHA-256 digest.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
