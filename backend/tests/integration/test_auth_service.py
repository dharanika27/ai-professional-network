"""Integration tests for app.services.auth_service against the live test DB.

Uses the `db_session` fixture (conftest.py handles rollback so no data leaks
between tests). Connection: postgresql+psycopg://app:app@localhost:5433/...
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.repositories.user_repository import DuplicateEmailError
from app.services import auth_service, security


@pytest.fixture()
def settings() -> Settings:
    return Settings()


def _unique_email(prefix: str = "authsvc") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@integration.test"


class TestAuthServiceIntegration:
    def test_full_register_login_refresh_cycle(
        self, db_session: Session, settings: Settings
    ) -> None:
        email = _unique_email("cycle")
        password = "goodpassword123"

        # Register
        user = auth_service.register(db_session, email, password, settings)
        db_session.flush()
        assert user.email == email.lower()
        assert user.password_hash.startswith("$argon2id$")

        # Login
        login_result = auth_service.login(db_session, email, password, settings)
        db_session.flush()
        assert login_result.user_id == user.id
        claims = security.decode_access_token(login_result.access_token, settings)
        assert claims["sub"] == str(user.id)

        # Refresh rotates the token: old becomes invalid, new is valid.
        refresh_result = auth_service.refresh(db_session, login_result.refresh_token, settings)
        db_session.flush()
        assert refresh_result.user_id == user.id
        assert refresh_result.refresh_token != login_result.refresh_token

        # Old refresh token can no longer be used.
        with pytest.raises(auth_service.AuthError):
            auth_service.refresh(db_session, login_result.refresh_token, settings)

    def test_duplicate_email_raises(self, db_session: Session, settings: Settings) -> None:
        email = _unique_email("dup")
        auth_service.register(db_session, email, "goodpassword123", settings)
        db_session.flush()

        with pytest.raises(DuplicateEmailError):
            auth_service.register(db_session, email, "anotherpassword", settings)

    def test_wrong_password_same_error_as_unknown_email(
        self, db_session: Session, settings: Settings
    ) -> None:
        email = _unique_email("enum")
        auth_service.register(db_session, email, "goodpassword123", settings)
        db_session.flush()

        with pytest.raises(auth_service.AuthError) as wrong_pw:
            auth_service.login(db_session, email, "wrongpassword", settings)

        with pytest.raises(auth_service.AuthError) as unknown:
            auth_service.login(db_session, _unique_email("ghost"), "whatever1", settings)

        assert type(wrong_pw.value) is type(unknown.value)
        assert str(wrong_pw.value) == str(unknown.value)
