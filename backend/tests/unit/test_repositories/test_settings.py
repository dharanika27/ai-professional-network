"""Tests for app/config/settings.py and app/config/llm_config.py.

F006-F009, AC-BEHAV-01, AC-BEHAV-02, AC-BEHAV-09, AC-IMPORT-05.
Tests pass _env_file=None to prevent local .env from leaking into the test.
For fail-fast tests, we also temporarily unset os.environ vars (pytest-env
injects them, so we must clear them during the test).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config.llm_config import LLMConfig, build_llm_config
from app.config.settings import Settings


def _make_settings(**overrides) -> Settings:
    """Create a Settings with required fields plus optional overrides.

    _env_file=None prevents local .env from injecting values.
    """
    defaults = {
        "database_url": "postgresql+psycopg://app:app@localhost:5433/ai_professional_network",
        "jwt_secret": "test-secret-not-a-real-key-for-tests-only",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


# ---------------------------------------------------------------------------
# AC-BEHAV-01: fail-fast on missing required secrets
# ---------------------------------------------------------------------------


class TestFailFastOnMissingSecrets:
    def test_missing_database_url_raises(self) -> None:
        """With DATABASE_URL unset, Settings must raise at load time naming DATABASE_URL."""
        # Clear both DATABASE_URL and JWT_SECRET from os.environ so pydantic-settings
        # can't find them (pytest-env injects them, _env_file=None doesn't help)
        env_without = {k: v for k, v in os.environ.items() if k.upper() not in ("DATABASE_URL",)}
        with patch.dict(os.environ, env_without, clear=True):
            with pytest.raises((ValidationError, Exception)) as exc_info:
                Settings(_env_file=None, jwt_secret="test-secret")
        error_str = str(exc_info.value).lower()
        assert "database_url" in error_str

    def test_missing_jwt_secret_raises(self) -> None:
        """With JWT_SECRET unset, Settings must raise at load time naming JWT_SECRET."""
        env_without = {k: v for k, v in os.environ.items() if k.upper() not in ("JWT_SECRET",)}
        with patch.dict(os.environ, env_without, clear=True):
            with pytest.raises((ValidationError, Exception)) as exc_info:
                Settings(
                    _env_file=None,
                    database_url="postgresql+psycopg://app:app@localhost:5433/ai_professional_network",
                )
        error_str = str(exc_info.value).lower()
        assert "jwt_secret" in error_str


# ---------------------------------------------------------------------------
# AC-BEHAV-09: loads successfully with ANTHROPIC_API_KEY and GROQ_API_KEY both unset
# ---------------------------------------------------------------------------


class TestNoAnthropicKeyRequired:
    def test_loads_without_groq_and_anthropic(self) -> None:
        """Amendment 001: neither ANTHROPIC_API_KEY nor GROQ_API_KEY must be set."""
        settings = _make_settings()
        # groq_api_key should be None (optional)
        assert settings.groq_api_key is None
        # settings loads successfully — no exception
        assert settings.database_url is not None
        assert settings.jwt_secret is not None

    def test_no_anthropic_api_key_field(self) -> None:
        """AC-IMPORT-05: anthropic_api_key must NOT be a required field."""
        settings = _make_settings()
        # The model should not have anthropic_api_key as an attribute
        assert not hasattr(settings, "anthropic_api_key")


# ---------------------------------------------------------------------------
# AC-BEHAV-02: typed fields for all config
# ---------------------------------------------------------------------------


class TestSettingsFields:
    def test_database_url_stored(self) -> None:
        s = _make_settings()
        assert "5433" in s.database_url

    def test_jwt_secret_stored(self) -> None:
        s = _make_settings()
        assert s.jwt_secret == "test-secret-not-a-real-key-for-tests-only"

    def test_jwt_access_ttl_default(self) -> None:
        s = _make_settings()
        assert s.jwt_access_ttl_seconds == 900

    def test_jwt_refresh_ttl_default(self) -> None:
        s = _make_settings()
        assert s.jwt_refresh_ttl_seconds == 2_592_000

    def test_llm_provider_default(self) -> None:
        s = _make_settings()
        assert s.llm_provider == "groq"

    def test_llm_timeout_default(self) -> None:
        """AC-BEHAV-02: llm_timeout_seconds defaults to 60."""
        s = _make_settings()
        assert s.llm_timeout_seconds == 60

    def test_ai_rate_limit_default(self) -> None:
        s = _make_settings()
        assert s.ai_rate_limit_per_hour == 10

    def test_embedding_model_default(self) -> None:
        s = _make_settings()
        assert s.embedding_model == "BAAI/bge-small-en-v1.5"

    def test_embedding_dim_default(self) -> None:
        s = _make_settings()
        assert s.embedding_dim == 384

    def test_max_upload_mb_default(self) -> None:
        """AC-BEHAV-02: max_upload_mb defaults to 5."""
        s = _make_settings()
        assert s.max_upload_mb == 5

    def test_max_upload_bytes_property(self) -> None:
        s = _make_settings()
        assert s.max_upload_bytes == 5 * 1024 * 1024

    def test_frontend_origin_default(self) -> None:
        s = _make_settings()
        assert s.frontend_origin == "http://localhost:3000"

    def test_invalid_max_upload_mb_raises(self) -> None:
        """AC-BEHAV-02: invalid-typed value (non-int MAX_UPLOAD_MB) raises validation error."""
        with pytest.raises((ValidationError, Exception)):
            Settings(
                _env_file=None,
                database_url="postgresql+psycopg://app:app@localhost:5433/ai_professional_network",
                jwt_secret="test-secret",
                max_upload_mb=0,  # 0 is invalid (validator requires > 0)
            )

    def test_groq_api_key_override(self) -> None:
        s = _make_settings(groq_api_key="gsk_fake_key_for_testing")
        assert s.groq_api_key == "gsk_fake_key_for_testing"


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------


class TestLLMConfig:
    def test_build_from_settings(self) -> None:
        """AC-BEHAV-02: LLM config reads from settings."""
        s = _make_settings()
        cfg = build_llm_config(s)
        assert isinstance(cfg, LLMConfig)
        assert cfg.provider == "groq"
        assert cfg.timeout_seconds == 60
        assert cfg.max_retries == 1
        assert cfg.ai_rate_limit_per_hour == 10

    def test_no_groq_key_in_config_is_none(self) -> None:
        s = _make_settings()
        cfg = build_llm_config(s)
        assert cfg.groq_api_key is None

    def test_groq_key_propagated(self) -> None:
        s = _make_settings(groq_api_key="gsk_fake_test_key")
        cfg = build_llm_config(s)
        assert cfg.groq_api_key == "gsk_fake_test_key"

    def test_config_is_immutable(self) -> None:
        """LLMConfig is a frozen dataclass."""
        s = _make_settings()
        cfg = build_llm_config(s)
        with pytest.raises((AttributeError, TypeError)):
            cfg.provider = "anthropic"  # type: ignore[misc]

    def test_review_model_is_set(self) -> None:
        s = _make_settings()
        cfg = build_llm_config(s)
        assert cfg.review_model != ""

    def test_default_model_is_set(self) -> None:
        s = _make_settings()
        cfg = build_llm_config(s)
        assert cfg.default_model != ""
