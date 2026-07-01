"""Unit tests for app.services.security.

Covers Argon2id hashing, HS256 JWT creation/verification, and opaque refresh
token generation/hashing. No database or FastAPI involvement.
"""

from __future__ import annotations

import time
import uuid

import pytest
from jose import JWTError

from app.config.settings import Settings
from app.services import security


@pytest.fixture()
def settings() -> Settings:
    """Settings built from env (pytest-env supplies JWT_SECRET/DATABASE_URL)."""
    return Settings()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_password_returns_argon2id_encoded_string(self, settings: Settings) -> None:
        hashed = security.hash_password("correct horse battery", settings)
        assert hashed.startswith("$argon2id$")

    def test_hash_password_is_salted_unique_per_call(self, settings: Settings) -> None:
        h1 = security.hash_password("same-password", settings)
        h2 = security.hash_password("same-password", settings)
        assert h1 != h2

    def test_verify_password_true_for_correct(self, settings: Settings) -> None:
        hashed = security.hash_password("s3cret-password", settings)
        assert security.verify_password("s3cret-password", hashed) is True

    def test_verify_password_false_for_wrong(self, settings: Settings) -> None:
        hashed = security.hash_password("s3cret-password", settings)
        assert security.verify_password("wrong-password", hashed) is False

    def test_verify_password_false_for_malformed_hash(self, settings: Settings) -> None:
        assert security.verify_password("anything", "not-a-real-hash") is False


# ---------------------------------------------------------------------------
# JWT access tokens
# ---------------------------------------------------------------------------


class TestAccessTokens:
    def test_create_access_token_returns_decodable_jwt(self, settings: Settings) -> None:
        user_id = uuid.uuid4()
        token, jti = security.create_access_token(user_id, settings)

        claims = security.decode_access_token(token, settings)
        assert claims["sub"] == str(user_id)
        assert claims["jti"] == jti
        assert "exp" in claims
        assert "iat" in claims

    def test_jti_is_valid_uuid_and_unique(self, settings: Settings) -> None:
        _, jti1 = security.create_access_token(uuid.uuid4(), settings)
        _, jti2 = security.create_access_token(uuid.uuid4(), settings)
        # jti parses as a UUID and is unique per call.
        uuid.UUID(jti1)
        assert jti1 != jti2

    def test_decode_raises_on_wrong_secret(self, settings: Settings) -> None:
        token, _ = security.create_access_token(uuid.uuid4(), settings)
        tampered = settings.model_copy(update={"jwt_secret": "a-different-secret"})
        with pytest.raises(JWTError):
            security.decode_access_token(token, tampered)

    def test_decode_raises_on_expired_token(self, settings: Settings) -> None:
        # Zero TTL: token expires immediately.
        short = settings.model_copy(update={"jwt_access_ttl_seconds": -1})
        token, _ = security.create_access_token(uuid.uuid4(), short)
        with pytest.raises(JWTError):
            security.decode_access_token(token, settings)

    def test_expiry_honors_access_ttl_seconds(self, settings: Settings) -> None:
        configured = settings.model_copy(update={"jwt_access_ttl_seconds": 900})
        before = int(time.time())
        token, _ = security.create_access_token(uuid.uuid4(), configured)
        claims = security.decode_access_token(token, configured)
        lifetime = claims["exp"] - claims["iat"]
        assert lifetime == 900
        # exp is roughly now + 900 (allow a couple seconds of clock skew).
        assert abs(claims["exp"] - (before + 900)) <= 5


# ---------------------------------------------------------------------------
# Opaque refresh tokens
# ---------------------------------------------------------------------------


class TestRefreshTokens:
    def test_generate_refresh_token_is_high_entropy_non_jwt(self) -> None:
        token = security.generate_refresh_token()
        assert isinstance(token, str)
        assert len(token) >= 32
        # Opaque token is not a 3-segment JWT.
        assert token.count(".") != 2

    def test_generate_refresh_token_unique_per_call(self) -> None:
        assert security.generate_refresh_token() != security.generate_refresh_token()

    def test_hash_refresh_token_is_sha256_hex(self) -> None:
        digest = security.hash_refresh_token("some-raw-token")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hash_refresh_token_is_deterministic(self) -> None:
        assert security.hash_refresh_token("abc") == security.hash_refresh_token("abc")
        assert security.hash_refresh_token("abc") != security.hash_refresh_token("abd")
