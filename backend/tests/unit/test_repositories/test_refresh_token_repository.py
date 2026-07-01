"""Unit tests for refresh_token_repository.py — F022, F023.

These tests use mocked sessions (no live DB) to verify:
- store_refresh_token calls session.add/flush and returns domain RefreshToken
- revoke_refresh_token sets revoked=True on the ORM row
- is_refresh_token_valid returns True only for non-revoked, non-expired tokens
- is_refresh_token_valid returns False for revoked, expired, or unknown tokens
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.repositories.refresh_token_repository import (
    is_refresh_token_valid,
    revoke_refresh_token,
    store_refresh_token,
)
from app.types.domain import RefreshToken


def _make_token_row(
    token_hash: str = "abc123",
    revoked: bool = False,
    expires_at: datetime | None = None,
) -> MagicMock:
    """Return a MagicMock that looks like a RefreshTokenModel ORM row."""
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(hours=1)
    row = MagicMock()
    row.id = uuid.uuid4()
    row.user_id = uuid.uuid4()
    row.token_hash = token_hash
    row.expires_at = expires_at
    row.revoked = revoked
    row.rotated_to = None
    row.created_at = datetime.now(UTC)
    return row


# ---------------------------------------------------------------------------
# store_refresh_token — happy path
# ---------------------------------------------------------------------------


class TestStoreRefreshToken:
    def test_returns_refresh_token_domain_model(self) -> None:
        """store_refresh_token must return a RefreshToken domain model."""
        session = MagicMock()
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(token_hash="sha256hash", expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            result = store_refresh_token(session, user_id, "sha256hash", expires_at)

        assert isinstance(result, RefreshToken)

    def test_calls_session_add(self) -> None:
        """store_refresh_token must call session.add."""
        session = MagicMock()
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            store_refresh_token(session, user_id, "hash", expires_at)

        session.add.assert_called_once()

    def test_calls_session_flush(self) -> None:
        """store_refresh_token must call session.flush() to populate UUID."""
        session = MagicMock()
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            store_refresh_token(session, user_id, "hash", expires_at)

        session.flush.assert_called_once()

    def test_never_calls_commit(self) -> None:
        """store_refresh_token must NOT call session.commit."""
        session = MagicMock()
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            store_refresh_token(session, user_id, "hash", expires_at)

        session.commit.assert_not_called()

    def test_never_calls_rollback(self) -> None:
        """store_refresh_token must NOT call session.rollback."""
        session = MagicMock()
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            store_refresh_token(session, user_id, "hash", expires_at)

        session.rollback.assert_not_called()

    def test_stored_token_has_correct_hash(self) -> None:
        """The returned RefreshToken must carry the provided token_hash."""
        session = MagicMock()
        user_id = uuid.uuid4()
        token_hash = "sha256_hex_value"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(token_hash=token_hash, expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            result = store_refresh_token(session, user_id, token_hash, expires_at)

        assert result.token_hash == token_hash

    def test_stored_token_revoked_false(self) -> None:
        """Newly stored token must have revoked=False."""
        session = MagicMock()
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        with patch("app.repositories.refresh_token_repository.RefreshTokenModel") as mock_cls:
            row = _make_token_row(revoked=False, expires_at=expires_at)
            row.user_id = user_id
            mock_cls.return_value = row
            result = store_refresh_token(session, user_id, "hash", expires_at)

        assert result.revoked is False


# ---------------------------------------------------------------------------
# revoke_refresh_token
# ---------------------------------------------------------------------------


class TestRevokeRefreshToken:
    def test_sets_revoked_true(self) -> None:
        """revoke_refresh_token must set row.revoked = True."""
        session = MagicMock()
        row = _make_token_row(revoked=False)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        revoke_refresh_token(session, "abc123")

        assert row.revoked is True

    def test_does_nothing_for_unknown_token(self) -> None:
        """revoke_refresh_token should not raise when token_hash is unknown."""
        session = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        # Should not raise
        revoke_refresh_token(session, "nonexistent_hash")

    def test_never_calls_commit(self) -> None:
        """revoke_refresh_token must NOT call session.commit."""
        session = MagicMock()
        row = _make_token_row()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        revoke_refresh_token(session, "abc123")
        session.commit.assert_not_called()

    def test_never_calls_rollback(self) -> None:
        """revoke_refresh_token must NOT call session.rollback."""
        session = MagicMock()
        row = _make_token_row()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        revoke_refresh_token(session, "abc123")
        session.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# is_refresh_token_valid
# ---------------------------------------------------------------------------


class TestIsRefreshTokenValid:
    def test_valid_active_token_returns_true(self) -> None:
        """Valid (non-revoked, non-expired) token → True."""
        session = MagicMock()
        future_time = datetime.now(UTC) + timedelta(hours=1)
        row = _make_token_row(revoked=False, expires_at=future_time)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        assert is_refresh_token_valid(session, "abc123") is True

    def test_revoked_token_returns_false(self) -> None:
        """Revoked token → False even if not expired."""
        session = MagicMock()
        future_time = datetime.now(UTC) + timedelta(hours=1)
        row = _make_token_row(revoked=True, expires_at=future_time)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        assert is_refresh_token_valid(session, "abc123") is False

    def test_expired_token_returns_false(self) -> None:
        """Expired token → False even if not revoked."""
        session = MagicMock()
        past_time = datetime.now(UTC) - timedelta(hours=1)
        row = _make_token_row(revoked=False, expires_at=past_time)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        assert is_refresh_token_valid(session, "abc123") is False

    def test_unknown_token_returns_false(self) -> None:
        """Unknown token hash → False (no row found)."""
        session = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        assert is_refresh_token_valid(session, "unknown_hash") is False

    def test_revoked_and_expired_token_returns_false(self) -> None:
        """Token that is both revoked and expired → False."""
        session = MagicMock()
        past_time = datetime.now(UTC) - timedelta(hours=1)
        row = _make_token_row(revoked=True, expires_at=past_time)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        assert is_refresh_token_valid(session, "abc123") is False

    def test_never_calls_commit(self) -> None:
        """is_refresh_token_valid must NOT call session.commit."""
        session = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        is_refresh_token_valid(session, "hash")
        session.commit.assert_not_called()

    def test_never_calls_rollback(self) -> None:
        """is_refresh_token_valid must NOT call session.rollback."""
        session = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        is_refresh_token_valid(session, "hash")
        session.rollback.assert_not_called()

    def test_tz_naive_expires_at_treated_as_utc(self) -> None:
        """Timezone-naive expires_at (stored by DB without tz) must be normalised to UTC.

        Covers refresh_token_repository.py line 134 — the `tzinfo is None` branch.
        A tz-naive future timestamp should still be recognised as valid.
        Use a large offset (30 days) so it is clearly in the future regardless of timezone.
        """
        session = MagicMock()
        # tz-naive future timestamp — DB may store datetimes without tz
        naive_future = datetime.now() + timedelta(days=30)
        assert naive_future.tzinfo is None, "test precondition: must be tz-naive"
        row = _make_token_row(revoked=False, expires_at=naive_future)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        result = is_refresh_token_valid(session, "hash")
        assert result is True, (
            "A tz-naive future expires_at must still be valid after UTC normalisation"
        )

    def test_tz_naive_expired_token_returns_false(self) -> None:
        """Tz-naive past expires_at normalised to UTC must be recognised as expired.

        Use a very large offset (30 days) so the token is unambiguously expired
        regardless of the local timezone offset.
        """
        session = MagicMock()
        naive_past = datetime.now() - timedelta(days=30)  # 30 days ago — clearly expired
        assert naive_past.tzinfo is None
        row = _make_token_row(revoked=False, expires_at=naive_past)

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        result = is_refresh_token_valid(session, "hash")
        assert result is False
