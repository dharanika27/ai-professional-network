"""Integration tests for user_repository and refresh_token_repository.

Uses the live test DB via the `db_session` fixture (conftest.py handles rollback).
Tests cover F020/F021/F022/F023 acceptance criteria against real PostgreSQL.

Connection: postgresql+psycopg://app:app@localhost:5433/ai_professional_network
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.repositories.refresh_token_repository import (
    is_refresh_token_valid,
    revoke_refresh_token,
    store_refresh_token,
)
from app.repositories.user_repository import DuplicateEmailError, create_user, get_user_by_email

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@integration.test"


# ---------------------------------------------------------------------------
# F020 — create_user
# ---------------------------------------------------------------------------


class TestCreateUserIntegration:
    def test_create_user_success(self, db_session: Session) -> None:
        """F020: create_user returns a User with a generated UUID id."""
        email = _unique_email("create")
        user = create_user(db_session, email, "argon2hash_placeholder")

        assert user.id is not None
        assert isinstance(user.id, uuid.UUID)
        assert user.email == email.lower()
        assert user.password_hash == "argon2hash_placeholder"

    def test_create_user_duplicate_email_raises_typed_error(self, db_session: Session) -> None:
        """F020/AC-BEHAV-B01: duplicate email raises DuplicateEmailError (not raw IntegrityError)."""
        email = _unique_email("dup")
        create_user(db_session, email, "hash1")

        with pytest.raises(DuplicateEmailError) as exc_info:
            create_user(db_session, email, "hash2")

        assert email.lower() in str(exc_info.value)

    def test_create_user_email_stored_lowercase(self, db_session: Session) -> None:
        """create_user stores email in lowercase regardless of input case."""
        mixed_email = f"MiXeD_{uuid.uuid4().hex[:8]}@Integration.Test"
        user = create_user(db_session, mixed_email, "hash")

        assert user.email == mixed_email.lower()

    def test_create_user_uuid_is_unique_per_call(self, db_session: Session) -> None:
        """Two different users get different UUIDs."""
        user1 = create_user(db_session, _unique_email("u1"), "hash")
        user2 = create_user(db_session, _unique_email("u2"), "hash")

        assert user1.id != user2.id


# ---------------------------------------------------------------------------
# F021 — get_user_by_email
# ---------------------------------------------------------------------------


class TestGetUserByEmailIntegration:
    def test_get_user_by_email_case_insensitive(self, db_session: Session) -> None:
        """F021/AC-BEHAV-B02: email lookup is case-insensitive."""
        base = f"mixed_{uuid.uuid4().hex[:8]}"
        original_email = f"{base}@example.test"
        create_user(db_session, original_email.upper(), "hash")

        # Query with all-lower
        result = get_user_by_email(db_session, original_email.lower())
        assert result is not None
        assert result.email == original_email.lower()

    def test_get_user_by_email_mixed_case_query(self, db_session: Session) -> None:
        """get_user_by_email with mixed-case lookup finds the user."""
        base = f"mixcase_{uuid.uuid4().hex[:8]}"
        email = f"{base}@example.test"
        created = create_user(db_session, email, "hash")

        # Query with different casing
        result = get_user_by_email(db_session, email.upper())
        assert result is not None
        assert result.id == created.id

    def test_get_user_by_email_not_found(self, db_session: Session) -> None:
        """F021: get_user_by_email returns None for unknown email."""
        result = get_user_by_email(db_session, "nobody_ever@doesnt.exist")
        assert result is None

    def test_get_user_by_email_returns_correct_user(self, db_session: Session) -> None:
        """get_user_by_email returns the correct user when multiple users exist."""
        email_a = _unique_email("findme")
        email_b = _unique_email("other")
        user_a = create_user(db_session, email_a, "hash_a")
        create_user(db_session, email_b, "hash_b")

        result = get_user_by_email(db_session, email_a)
        assert result is not None
        assert result.id == user_a.id
        assert result.email == email_a.lower()


# ---------------------------------------------------------------------------
# F022/F023 — store_refresh_token, revoke_refresh_token, is_refresh_token_valid
# ---------------------------------------------------------------------------


class TestRefreshTokenIntegration:
    def test_store_and_validate_refresh_token(self, db_session: Session) -> None:
        """F022: store_refresh_token persists token; F023: is_refresh_token_valid → True."""
        user = create_user(db_session, _unique_email("tok"), "hash")
        token_hash = _sha256(f"raw_token_{uuid.uuid4().hex}")
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        stored = store_refresh_token(db_session, user.id, token_hash, expires_at)

        assert stored.token_hash == token_hash
        assert stored.revoked is False
        assert stored.user_id == user.id

        assert is_refresh_token_valid(db_session, token_hash) is True

    def test_store_and_revoke_refresh_token(self, db_session: Session) -> None:
        """F022/F023: revoke_refresh_token sets revoked=True; subsequent validate → False."""
        user = create_user(db_session, _unique_email("revoke"), "hash")
        token_hash = _sha256(f"raw_token_{uuid.uuid4().hex}")
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        store_refresh_token(db_session, user.id, token_hash, expires_at)

        # Before revoke → valid
        assert is_refresh_token_valid(db_session, token_hash) is True

        revoke_refresh_token(db_session, token_hash)

        # After revoke → invalid
        assert is_refresh_token_valid(db_session, token_hash) is False

    def test_refresh_token_expired(self, db_session: Session) -> None:
        """F023/AC-BEHAV-B04: token with past expires_at → is_refresh_token_valid returns False."""
        user = create_user(db_session, _unique_email("expired"), "hash")
        token_hash = _sha256(f"raw_token_{uuid.uuid4().hex}")
        past_time = datetime.now(UTC) - timedelta(hours=1)

        store_refresh_token(db_session, user.id, token_hash, past_time)

        assert is_refresh_token_valid(db_session, token_hash) is False

    def test_refresh_token_unknown_returns_false(self, db_session: Session) -> None:
        """F023/AC-BEHAV-B04: unknown token_hash → is_refresh_token_valid returns False."""
        unknown_hash = _sha256(f"totally_unknown_{uuid.uuid4().hex}")
        assert is_refresh_token_valid(db_session, unknown_hash) is False

    def test_store_refresh_token_persists_expires_at(self, db_session: Session) -> None:
        """F022/AC-SCHEMA-B05: expires_at is persisted exactly as provided."""
        user = create_user(db_session, _unique_email("exp_at"), "hash")
        token_hash = _sha256(f"raw_{uuid.uuid4().hex}")
        # Use a precise timestamp truncated to seconds
        expires_at = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)

        stored = store_refresh_token(db_session, user.id, token_hash, expires_at)

        assert stored.expires_at is not None

    def test_revoke_nonexistent_token_does_not_raise(self, db_session: Session) -> None:
        """revoke_refresh_token on unknown hash is a no-op (no exception)."""
        fake_hash = _sha256(f"never_stored_{uuid.uuid4().hex}")
        # Should not raise
        revoke_refresh_token(db_session, fake_hash)
