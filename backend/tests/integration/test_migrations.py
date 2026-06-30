"""Integration tests for Alembic migrations — F010, F012, F014.

Requires: live DB at TEST_DATABASE_URL, alembic upgrade head already applied.
These tests verify the schema state AFTER migration, not the migration process itself
(running alembic CLI is verified by the ratchet gate commands).
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

TEST_DATABASE_URL = (
    os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:5433/ai_professional_network")
    .replace("postgresql://", "postgresql+psycopg://", 1)
    .replace("postgres://", "postgresql+psycopg://", 1)
)


@pytest.fixture(scope="module")
def live_engine() -> sa.Engine:
    """Module-scoped engine for migration integration tests."""
    engine = sa.create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


class TestPgvectorExtension:
    """F010: pgvector extension exists after migration."""

    def test_vector_extension_present(self, live_engine: sa.Engine) -> None:
        """After alembic upgrade head, vector extension must exist."""
        with live_engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT extname FROM pg_extension WHERE extname='vector'")
            ).fetchone()
        assert row is not None, "pgvector extension not found; run 'alembic upgrade head'"
        assert row[0] == "vector"


class TestVectorColumnsAreMigrated:
    """F012: migrated vector columns are exactly vector(384)."""

    def test_resumes_embedding_is_vector_384(self, live_engine: sa.Engine) -> None:
        """AC-SCHEMA-05 + migrated_vector_columns_are_384: resumes.embedding is vector(384)."""
        self._assert_vector_384(live_engine, "resumes", "embedding")

    def test_jobs_embedding_is_vector_384(self, live_engine: sa.Engine) -> None:
        self._assert_vector_384(live_engine, "jobs", "embedding")

    def test_knowledge_chunks_embedding_is_vector_384(self, live_engine: sa.Engine) -> None:
        self._assert_vector_384(live_engine, "knowledge_chunks", "embedding")

    def _assert_vector_384(self, engine: sa.Engine, table: str, column: str) -> None:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a "
                    "JOIN pg_class c ON a.attrelid = c.oid "
                    "WHERE c.relname = :tbl AND a.attname = :col AND a.attnum > 0"
                ),
                {"tbl": table, "col": column},
            ).fetchone()
        assert row is not None, f"Column {table}.{column} not found. Run 'alembic upgrade head'."
        fmt = str(row[0]).replace(" ", "")
        assert fmt.endswith("(384)"), f"Expected vector(384) for {table}.{column}, got {row[0]!r}"


class TestHNSWIndexes:
    """HNSW cosine indexes exist on vector columns."""

    def test_resumes_hnsw_index(self, live_engine: sa.Engine) -> None:
        self._assert_index_exists(live_engine, "resumes_embedding_hnsw")

    def test_jobs_hnsw_index(self, live_engine: sa.Engine) -> None:
        self._assert_index_exists(live_engine, "jobs_embedding_hnsw")

    def test_knowledge_chunks_hnsw_index(self, live_engine: sa.Engine) -> None:
        self._assert_index_exists(live_engine, "knowledge_chunks_embedding_hnsw")

    def _assert_index_exists(self, engine: sa.Engine, index_name: str) -> None:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE indexname = :name"),
                {"name": index_name},
            ).fetchone()
        assert row is not None, f"HNSW index {index_name!r} not found"


class TestVectorDistanceOperator:
    """Smoke test: vector(384) columns support <-> (L2 distance) operator."""

    def test_vector_distance_op_works(self, live_engine: sa.Engine) -> None:
        """pgvector_smoke_384_and_distance equivalent."""
        with live_engine.connect() as conn:
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(sa.text("DROP TABLE IF EXISTS _test_vec_smoke"))
            conn.execute(sa.text("CREATE TABLE _test_vec_smoke (id int, v vector(384))"))
            conn.execute(
                sa.text(
                    "INSERT INTO _test_vec_smoke VALUES "
                    "(1, (SELECT '['||string_agg('0',',')||']' "
                    "FROM generate_series(1,384))::vector)"
                )
            )
            row = conn.execute(sa.text("SELECT v <-> v FROM _test_vec_smoke")).fetchone()
            conn.execute(sa.text("DROP TABLE _test_vec_smoke"))
            conn.commit()
        assert row is not None
        # L2 distance of a vector with itself is 0
        assert float(row[0]) == pytest.approx(0.0, abs=1e-6)


class TestAllTablesExist:
    """All 11 tables from the schema exist after migration."""

    EXPECTED_TABLES = {
        "users",
        "refresh_tokens",
        "profiles",
        "resumes",
        "resume_reviews",
        "profile_optimizations",
        "jobs",
        "job_match_runs",
        "job_matches",
        "knowledge_chunks",
        "ai_request_logs",
    }

    def test_all_tables_present(self, live_engine: sa.Engine) -> None:
        with live_engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).fetchall()
        existing = {row[0] for row in rows}
        missing = self.EXPECTED_TABLES - existing
        assert not missing, f"Missing tables after migration: {missing}"
