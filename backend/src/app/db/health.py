"""Database health-check function.

Executes SELECT 1 against the database and returns a typed health status.
Used by the API /health endpoint (E2-S3 AC4).
"""

from __future__ import annotations

import logging
from typing import Literal, TypedDict

import sqlalchemy as sa

from app.db.session import get_engine

logger = logging.getLogger(__name__)


class DBHealthStatus(TypedDict):
    """Typed health check result."""

    status: Literal["healthy", "unhealthy"]
    detail: str


def check_db_health() -> DBHealthStatus:
    """Execute SELECT 1 and return a health status dict.

    Returns ``{"status": "healthy", "detail": "..."}`` on success.
    Returns ``{"status": "unhealthy", "detail": "<error>"}`` on any failure.
    Never raises — callers (the /health endpoint) decide the HTTP status code.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return {"status": "healthy", "detail": "SELECT 1 succeeded"}
    except Exception as exc:  # noqa: BLE001 — intentional catch-all for health probe
        logger.warning("DB health check failed", extra={"error": str(exc)})
        return {"status": "unhealthy", "detail": str(exc)}
