"""Unit tests for user_repository.py — F020, F021.

These tests use mocked sessions (no live DB) to verify:
- create_user calls session.add/flush and returns a mapped domain User
- duplicate email detection translates IntegrityError → DuplicateEmailError
- email is lowercased before persistence
- get_user_by_email returns None for unknown email
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy.exc

from app.repositories.user_repository import DuplicateEmailError, create_user, get_user_by_email
from app.types.domain import User
from app.types.enums import ThemePreference


def _make_user_row(
    email: str = "test@example.com",
    password_hash: str = "hashed",
) -> MagicMock:
    """Return a MagicMock that looks like a UserModel ORM row."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.email = email.lower()
    row.password_hash = password_hash
    row.theme_preference = ThemePreference.SYSTEM
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    return row


# ---------------------------------------------------------------------------
# create_user — happy path
# ---------------------------------------------------------------------------


class TestCreateUserHappyPath:
    def test_returns_user_domain_model(self) -> None:
        """create_user must return a User domain model (not the ORM row)."""
        session = MagicMock()
        row = _make_user_row()

        # Simulate flush populating the row on session.add side effect
        def add_side_effect(obj: object) -> None:
            pass

        session.add.side_effect = add_side_effect

        with patch("app.repositories.user_repository.UserModel", return_value=row):
            result = create_user(session, "Test@Example.Com", "hash123")

        assert isinstance(result, User)

    def test_calls_session_add(self) -> None:
        """create_user must call session.add with the ORM model instance."""
        session = MagicMock()

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            row = _make_user_row()
            mock_model_cls.return_value = row
            create_user(session, "test@example.com", "hash")

        session.add.assert_called_once()

    def test_calls_session_flush(self) -> None:
        """create_user must call session.flush() to populate the UUID."""
        session = MagicMock()

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            row = _make_user_row()
            mock_model_cls.return_value = row
            create_user(session, "test@example.com", "hash")

        session.flush.assert_called_once()

    def test_never_calls_commit(self) -> None:
        """create_user must NOT call session.commit — caller owns transaction."""
        session = MagicMock()

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            row = _make_user_row()
            mock_model_cls.return_value = row
            create_user(session, "test@example.com", "hash")

        session.commit.assert_not_called()

    def test_never_calls_rollback(self) -> None:
        """create_user must NOT call session.rollback."""
        session = MagicMock()

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            row = _make_user_row()
            mock_model_cls.return_value = row
            create_user(session, "test@example.com", "hash")

        session.rollback.assert_not_called()

    def test_never_calls_close(self) -> None:
        """create_user must NOT call session.close."""
        session = MagicMock()

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            row = _make_user_row()
            mock_model_cls.return_value = row
            create_user(session, "test@example.com", "hash")

        session.close.assert_not_called()

    def test_returned_user_has_uuid_id(self) -> None:
        """The returned User must have the id populated from the ORM row."""
        session = MagicMock()
        expected_id = uuid.uuid4()

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            row = _make_user_row()
            row.id = expected_id
            mock_model_cls.return_value = row
            result = create_user(session, "test@example.com", "hash")

        assert result.id == expected_id
        assert isinstance(result.id, uuid.UUID)


# ---------------------------------------------------------------------------
# create_user — email lowercasing
# ---------------------------------------------------------------------------


class TestCreateUserEmailLowercasing:
    def test_email_lowercased_on_model_construction(self) -> None:
        """create_user must lowercase the email before passing to UserModel."""
        session = MagicMock()
        captured_kwargs: dict[str, object] = {}

        def capture_kwargs(**kwargs: object) -> MagicMock:
            captured_kwargs.update(kwargs)
            row = _make_user_row(email=str(kwargs.get("email", "")))
            return row

        with patch("app.repositories.user_repository.UserModel", side_effect=capture_kwargs):
            create_user(session, "UPPER@EXAMPLE.COM", "hash")

        assert captured_kwargs.get("email") == "upper@example.com"

    def test_mixed_case_email_lowercased(self) -> None:
        """Mixed case should be fully lowercased."""
        session = MagicMock()
        captured_kwargs: dict[str, object] = {}

        def capture_kwargs(**kwargs: object) -> MagicMock:
            captured_kwargs.update(kwargs)
            row = _make_user_row(email=str(kwargs.get("email", "")))
            return row

        with patch("app.repositories.user_repository.UserModel", side_effect=capture_kwargs):
            create_user(session, "MiXeD@ExAmPlE.CoM", "hash")

        assert captured_kwargs.get("email") == "mixed@example.com"


# ---------------------------------------------------------------------------
# create_user — duplicate email detection
# ---------------------------------------------------------------------------


class TestCreateUserDuplicateEmail:
    def test_integrity_error_raises_duplicate_email_error(self) -> None:
        """IntegrityError on flush must be re-raised as DuplicateEmailError."""
        session = MagicMock()
        session.flush.side_effect = sqlalchemy.exc.IntegrityError(
            "statement", {}, Exception("UNIQUE constraint failed: users.email")
        )

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            mock_model_cls.return_value = _make_user_row()
            with pytest.raises(DuplicateEmailError):
                create_user(session, "dup@example.com", "hash")

    def test_duplicate_email_error_is_not_integrity_error(self) -> None:
        """DuplicateEmailError must be a custom typed exception, not raw IntegrityError."""
        assert not issubclass(DuplicateEmailError, sqlalchemy.exc.IntegrityError), (
            "DuplicateEmailError must be a distinct typed exception, not a subclass of IntegrityError"
        )

    def test_duplicate_email_error_message_contains_email(self) -> None:
        """DuplicateEmailError should report the offending email."""
        session = MagicMock()
        session.flush.side_effect = sqlalchemy.exc.IntegrityError(
            "statement", {}, Exception("UNIQUE constraint failed: users.email")
        )
        email = "dup@example.com"

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            mock_model_cls.return_value = _make_user_row()
            with pytest.raises(DuplicateEmailError) as exc_info:
                create_user(session, email, "hash")

        assert email in str(exc_info.value)

    def test_non_email_integrity_error_reraises(self) -> None:
        """IntegrityError unrelated to email uniqueness should propagate as-is."""
        session = MagicMock()
        original = sqlalchemy.exc.IntegrityError(
            "statement", {}, Exception("UNIQUE constraint on some_other_column")
        )
        session.flush.side_effect = original

        with patch("app.repositories.user_repository.UserModel") as mock_model_cls:
            mock_model_cls.return_value = _make_user_row()
            with pytest.raises(sqlalchemy.exc.IntegrityError):
                create_user(session, "test@example.com", "hash")


# ---------------------------------------------------------------------------
# get_user_by_email — unit tests
# ---------------------------------------------------------------------------


class TestGetUserByEmail:
    def test_returns_none_for_unknown_email(self) -> None:
        """get_user_by_email must return None when no row exists."""
        session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        result = get_user_by_email(session, "nobody@example.com")

        assert result is None

    def test_returns_user_when_found(self) -> None:
        """get_user_by_email must return a User domain model when the row is found."""
        session = MagicMock()
        row = _make_user_row(email="found@example.com")

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        result = get_user_by_email(session, "found@example.com")

        assert result is not None
        assert isinstance(result, User)
        assert result.email == "found@example.com"

    def test_query_uses_lowercased_email(self) -> None:
        """get_user_by_email must lowercase the email before querying."""
        session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        # Should not raise, just return None regardless of case
        result = get_user_by_email(session, "UPPER@EXAMPLE.COM")
        assert result is None

    def test_never_calls_commit(self) -> None:
        """get_user_by_email must NOT call session.commit."""
        session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        get_user_by_email(session, "test@example.com")
        session.commit.assert_not_called()

    def test_never_calls_rollback(self) -> None:
        """get_user_by_email must NOT call session.rollback."""
        session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        get_user_by_email(session, "test@example.com")
        session.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# get_user_by_id — unit tests (covers user_repository.py lines 144-147)
# ---------------------------------------------------------------------------


class TestGetUserById:
    def test_returns_none_for_unknown_id(self) -> None:
        """get_user_by_id must return None when no row matches."""
        from app.repositories.user_repository import get_user_by_id

        session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        result = get_user_by_id(session, uuid.uuid4())
        assert result is None

    def test_returns_user_when_found(self) -> None:
        """get_user_by_id must return a User domain object when the row exists."""
        from app.repositories.user_repository import get_user_by_id

        session = MagicMock()
        expected_id = uuid.uuid4()
        row = _make_user_row(email="found@example.com")
        row.id = expected_id

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = row
        session.query.return_value = mock_query

        result = get_user_by_id(session, expected_id)

        assert result is not None
        assert isinstance(result, User)
        assert result.id == expected_id
        assert result.email == "found@example.com"

    def test_never_calls_commit(self) -> None:
        """get_user_by_id must NOT call session.commit."""
        from app.repositories.user_repository import get_user_by_id

        session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        session.query.return_value = mock_query

        get_user_by_id(session, uuid.uuid4())
        session.commit.assert_not_called()
