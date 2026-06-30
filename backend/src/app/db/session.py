"""Database engine and session factory — the single import point for sessions.

Repositories must ONLY import sessions from here, never create their own engines.
Uses synchronous psycopg (v3) driver as required by the sprint contract.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Module-level singletons — initialized once via init_db() or create_engine_from_url()
_engine: sa.Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _ensure_psycopg_scheme(database_url: str) -> str:
    """Rewrite postgresql:// to postgresql+psycopg:// if needed.

    The sprint contract requires the synchronous psycopg v3 driver.
    """
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return database_url


def init_db(database_url: str) -> None:
    """Initialize the module-level engine and session factory.

    Call once at application startup. Safe to call multiple times
    (reinitializes, disposing the old engine).
    """
    global _engine, _session_factory

    url = _ensure_psycopg_scheme(database_url)

    if _engine is not None:
        _engine.dispose()

    _engine = sa.create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    _session_factory = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized", extra={"url_scheme": url.split("://")[0]})


def get_engine() -> sa.Engine:
    """Return the initialized engine. Raises if init_db() was not called."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db(database_url) first.")
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the initialized session factory."""
    if _session_factory is None:
        raise RuntimeError("Session factory not initialized. Call init_db(database_url) first.")
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    """Yield a scoped database session.

    Commits on success, rolls back on exception, always closes.
    Use as a FastAPI dependency: ``session: Session = Depends(get_session)``.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
