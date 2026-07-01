"""Unit tests for app.services.auth_service.

Repositories are mocked so these tests need no database. They verify the
security-critical behaviours: password-length gating before hashing, no user
enumeration, opaque refresh tokens, single-use rotation, and that only the
SHA-256 hash of a refresh token is ever persisted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config.settings import Settings
from app.repositories.user_repository import DuplicateEmailError
from app.services import auth_service, security
from app.types.domain import User
from app.types.enums import ThemePreference


@pytest.fixture()
def settings() -> Settings:
    return Settings()


@pytest.fixture()
def session() -> MagicMock:
    """A stand-in Session; repositories are patched so it is never used directly."""
    return MagicMock(name="session")


def _make_user(password_hash: str, email: str = "user@example.test") -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=password_hash,
        theme_preference=ThemePreference.SYSTEM,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_valid_creates_user_and_hashes_password(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_create_user(session: Any, email: str, password_hash: str) -> User:
            captured["email"] = email
            captured["password_hash"] = password_hash
            return _make_user(password_hash, email)

        monkeypatch.setattr(auth_service.user_repository, "create_user", fake_create_user)

        user = auth_service.register(session, "new@example.test", "goodpassword", settings)

        assert isinstance(user, User)
        # Password was hashed with Argon2id, plaintext never passed to the repo.
        assert captured["password_hash"].startswith("$argon2id$")
        assert captured["password_hash"] != "goodpassword"
        assert security.verify_password("goodpassword", captured["password_hash"]) is True

    def test_register_short_password_raises_before_any_db_call(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        create_spy = MagicMock()
        hash_spy = MagicMock()
        monkeypatch.setattr(auth_service.user_repository, "create_user", create_spy)
        monkeypatch.setattr(auth_service.security, "hash_password", hash_spy)

        with pytest.raises(auth_service.PasswordTooShortError):
            auth_service.register(session, "short@example.test", "short", settings)

        create_spy.assert_not_called()
        hash_spy.assert_not_called()

    def test_register_duplicate_email_propagates(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_dup(session: Any, email: str, password_hash: str) -> User:
            raise DuplicateEmailError(email)

        monkeypatch.setattr(auth_service.user_repository, "create_user", raise_dup)

        with pytest.raises(DuplicateEmailError):
            auth_service.register(session, "dup@example.test", "goodpassword", settings)


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_correct_credentials_returns_tokens(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        password = "goodpassword"
        user = _make_user(security.hash_password(password, settings))
        monkeypatch.setattr(auth_service.user_repository, "get_user_by_email", lambda **kw: user)
        store_spy = MagicMock()
        monkeypatch.setattr(auth_service.refresh_token_repository, "store_refresh_token", store_spy)

        result = auth_service.login(session, user.email, password, settings)

        assert result.user_id == user.id
        # Access token is a decodable JWT with the right subject.
        claims = security.decode_access_token(result.access_token, settings)
        assert claims["sub"] == str(user.id)
        # Refresh token is opaque, not a JWT.
        assert result.refresh_token.count(".") != 2

    def test_login_wrong_password_raises_autherror(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = _make_user(security.hash_password("goodpassword", settings))
        monkeypatch.setattr(auth_service.user_repository, "get_user_by_email", lambda **kw: user)

        with pytest.raises(auth_service.AuthError) as exc_info:
            auth_service.login(session, user.email, "wrongpassword", settings)

        self._wrong_password_message = str(exc_info.value)

    def test_login_unknown_email_same_error_as_wrong_password(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Unknown email path.
        monkeypatch.setattr(auth_service.user_repository, "get_user_by_email", lambda **kw: None)
        with pytest.raises(auth_service.AuthError) as unknown_exc:
            auth_service.login(session, "nobody@example.test", "whatever1", settings)

        # Wrong password path.
        user = _make_user(security.hash_password("goodpassword", settings))
        monkeypatch.setattr(auth_service.user_repository, "get_user_by_email", lambda **kw: user)
        with pytest.raises(auth_service.AuthError) as wrong_exc:
            auth_service.login(session, user.email, "wrongpassword", settings)

        # Identical error type AND message — no enumeration signal.
        assert type(unknown_exc.value) is type(wrong_exc.value)
        assert str(unknown_exc.value) == str(wrong_exc.value)

    def test_login_stores_only_sha256_hash_never_raw(
        self, session: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        password = "goodpassword"
        user = _make_user(security.hash_password(password, settings))
        monkeypatch.setattr(auth_service.user_repository, "get_user_by_email", lambda **kw: user)
        store_spy = MagicMock()
        monkeypatch.setattr(auth_service.refresh_token_repository, "store_refresh_token", store_spy)

        result = auth_service.login(session, user.email, password, settings)

        store_spy.assert_called_once()
        stored_hash = store_spy.call_args.kwargs["token_hash"]
        # What was persisted is the SHA-256 of the raw token, not the raw token.
        assert stored_hash != result.refresh_token
        assert stored_hash == security.hash_refresh_token(result.refresh_token)
        assert len(stored_hash) == 64


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    def _patch_repos(
        self, monkeypatch: pytest.MonkeyPatch, valid: bool, old_row: Any, new_row: Any
    ) -> MagicMock:
        monkeypatch.setattr(
            auth_service.refresh_token_repository,
            "is_refresh_token_valid",
            lambda **kw: valid,
        )
        monkeypatch.setattr(
            auth_service.refresh_token_repository,
            "store_refresh_token",
            MagicMock(),
        )
        # session.query(...).filter(...).first() returns old_row then new_row.
        query_result = MagicMock()
        query_result.filter.return_value.first.side_effect = [old_row, new_row]
        session = MagicMock()
        session.query.return_value = query_result
        return session

    def test_refresh_valid_returns_new_tokens_and_revokes_old(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_id = uuid.uuid4()
        old_row = MagicMock(user_id=user_id, revoked=False, rotated_to=None)
        new_row = MagicMock(id=uuid.uuid4())
        session = self._patch_repos(monkeypatch, valid=True, old_row=old_row, new_row=new_row)

        result = auth_service.refresh(session, "raw-refresh-token", settings)

        assert result.user_id == user_id
        # Old token revoked and linked to the replacement.
        assert old_row.revoked is True
        assert old_row.rotated_to == new_row.id
        # New refresh token is opaque and different from what was presented.
        assert result.refresh_token != "raw-refresh-token"
        assert result.refresh_token.count(".") != 2
        # New access token is a valid JWT for this user.
        claims = security.decode_access_token(result.access_token, settings)
        assert claims["sub"] == str(user_id)

    def test_refresh_invalid_token_raises_autherror(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = self._patch_repos(monkeypatch, valid=False, old_row=None, new_row=None)
        with pytest.raises(auth_service.AuthError):
            auth_service.refresh(session, "revoked-or-unknown", settings)
