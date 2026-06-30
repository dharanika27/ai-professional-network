"""Shared pytest fixtures for Group A tests.

All fixtures that need a live DB use the TEST_DATABASE_URL.
Settings-related fixtures pass _env_file=None to prevent local .env leaking.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = (
    os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:5433/ai_professional_network")
    .replace("postgresql://", "postgresql+psycopg://", 1)
    .replace("postgres://", "postgresql+psycopg://", 1)
)


@pytest.fixture(scope="session")
def db_engine() -> sa.Engine:
    """Session-scoped synchronous engine for the test DB."""
    engine = sa.create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def db_session_factory(db_engine: sa.Engine) -> sessionmaker[Session]:
    """Session factory bound to the test engine."""
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture()
def db_session(db_session_factory: sessionmaker[Session]) -> Session:
    """Provide a test DB session; rolls back after each test."""
    session = db_session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
