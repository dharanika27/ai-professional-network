"""Tests for app/db/health.py — F013, AC-BEHAV-03.

Tests the DB health check function against the live DB and an unreachable DSN.
"""

from __future__ import annotations

import os

from app.db.health import check_db_health
from app.db.session import init_db

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://app:app@localhost:5433/ai_professional_network",
)

UNREACHABLE_URL = "postgresql://app:app@localhost:9999/nonexistent"


class TestCheckDBHealth:
    def test_healthy_against_live_db(self) -> None:
        """AC-BEHAV-03: health check returns healthy against live DB."""
        init_db(TEST_DATABASE_URL)
        result = check_db_health()
        assert result["status"] == "healthy"
        assert "SELECT 1" in result["detail"] or result["detail"] != ""

    def test_unhealthy_against_unreachable_dsn(self) -> None:
        """AC-BEHAV-03: pointed at unreachable DSN, returns unhealthy (never raises)."""
        init_db(UNREACHABLE_URL)
        result = check_db_health()
        # Must return unhealthy, not raise
        assert result["status"] == "unhealthy"
        assert isinstance(result["detail"], str)

    def test_never_raises_on_unhealthy(self) -> None:
        """health check must not propagate exceptions."""
        init_db(UNREACHABLE_URL)
        # If this raises, the test will fail — that's the point
        result = check_db_health()
        assert result["status"] in {"healthy", "unhealthy"}

    def test_returns_typed_dict(self) -> None:
        init_db(TEST_DATABASE_URL)
        result = check_db_health()
        assert "status" in result
        assert "detail" in result
        assert result["status"] in {"healthy", "unhealthy"}
