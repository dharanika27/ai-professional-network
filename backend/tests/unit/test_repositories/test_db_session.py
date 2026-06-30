"""Tests for app/db/session.py — F011, AC-IMPORT-04, AC-BEHAV-03.

Tests the session factory, engine initialization, and DB health check
against the live test database.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.session import (
    _ensure_psycopg_scheme,
    get_engine,
    get_session,
    get_session_factory,
    init_db,
)

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://app:app@localhost:5433/ai_professional_network",
)


# ---------------------------------------------------------------------------
# _ensure_psycopg_scheme
# ---------------------------------------------------------------------------


class TestEnsurePsycopgScheme:
    def test_rewrites_postgresql_to_psycopg(self) -> None:
        url = "postgresql://user:pass@localhost:5432/db"
        result = _ensure_psycopg_scheme(url)
        assert result.startswith("postgresql+psycopg://")

    def test_rewrites_postgres_alias(self) -> None:
        url = "postgres://user:pass@localhost:5432/db"
        result = _ensure_psycopg_scheme(url)
        assert result.startswith("postgresql+psycopg://")

    def test_leaves_already_psycopg_unchanged(self) -> None:
        url = "postgresql+psycopg://user:pass@localhost:5432/db"
        result = _ensure_psycopg_scheme(url)
        assert result == url

    def test_leaves_asyncpg_unchanged(self) -> None:
        url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        result = _ensure_psycopg_scheme(url)
        assert result == url


# ---------------------------------------------------------------------------
# init_db and engine/session factory
# ---------------------------------------------------------------------------


class TestInitDB:
    def test_get_engine_before_init_raises(self) -> None:
        """Before init_db is called, get_engine must raise RuntimeError."""
        from app.db import session as sess_module

        original = sess_module._engine
        sess_module._engine = None
        try:
            with pytest.raises(RuntimeError, match="not initialized"):
                get_engine()
        finally:
            sess_module._engine = original

    def test_init_db_creates_engine(self) -> None:
        init_db(TEST_DATABASE_URL)
        engine = get_engine()
        assert engine is not None

    def test_get_session_factory_returns_callable(self) -> None:
        init_db(TEST_DATABASE_URL)
        factory = get_session_factory()
        assert callable(factory)

    def test_session_generator_yields_session(self) -> None:
        """F011: get_session() yields a usable Session."""
        init_db(TEST_DATABASE_URL)
        gen = get_session()
        session = next(gen)
        assert isinstance(session, Session)
        try:
            next(gen)
        except StopIteration:
            pass

    def test_session_can_execute_select_1(self) -> None:
        """Session from factory can execute SELECT 1 against live DB."""
        init_db(TEST_DATABASE_URL)
        factory = get_session_factory()
        session = factory()
        try:
            result = session.execute(sa.text("SELECT 1")).fetchone()
            assert result is not None
            assert result[0] == 1
        finally:
            session.close()
