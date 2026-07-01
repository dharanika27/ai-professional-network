"""Unit tests for job_repository.py (pure logic, no live DB).

Uses mock sessions so no database connection is required.

Tests:
  - test_retrieve_top_jobs_uses_cosine_operator  — verify <=> operator in query
  - test_get_job_by_id_returns_none_when_missing — mock query returns None
  - test_upsert_job_skips_existing_external_ref  — mock SELECT returns existing row
  - test_job_loader_protocol_substitutable       — stub class satisfies JobLoader Protocol
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from app.repositories.job_repository import (
    get_job_by_id,
    get_job_count,
    retrieve_top_jobs,
    upsert_job,
)
from seeds.loaders.job_loader import JobLoader, JobRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job_record(
    external_ref: str = "seed-000001",
    title: str = "Python Developer",
    company: str = "Nimbus Cloud",
    location: str = "Bengaluru, India",
    employment_type: str | None = "full_time",
    description: str = "Build scalable Python APIs.",
    skills: list[str] | None = None,
    seniority: str | None = "mid",
    source: str = "seed",
) -> JobRecord:
    return JobRecord(
        external_ref=external_ref,
        title=title,
        company=company,
        location=location,
        employment_type=employment_type,
        description=description,
        skills=skills or ["Python", "FastAPI"],
        seniority=seniority,
        source=source,
    )


def _make_job_model_row(job_id: uuid.UUID | None = None) -> Any:
    """Return a MagicMock mimicking a JobModel row."""
    row = MagicMock()
    row.id = job_id or uuid.uuid4()
    row.external_ref = "seed-000001"
    row.title = "Python Developer"
    row.company = "Nimbus Cloud"
    row.location = "Bengaluru, India"
    row.employment_type = "full_time"
    row.description = "Build scalable Python APIs."
    row.skills = ["Python", "FastAPI"]
    row.seniority = "mid"
    row.embedding = [0.1] * 384
    row.source = "seed"
    row.created_at = datetime.now(tz=UTC)
    return row


def _make_session() -> Any:
    """Return a MagicMock that mimics a minimal SQLAlchemy Session."""
    session = MagicMock()
    session.add.return_value = None
    session.flush.return_value = None
    return session


# ---------------------------------------------------------------------------
# test_retrieve_top_jobs_uses_cosine_operator
# ---------------------------------------------------------------------------


class TestRetrieveTopJobsUsesCosineSimilarity:
    def test_retrieve_top_jobs_uses_cosine_operator(self) -> None:
        """retrieve_top_jobs must use the <=> pgvector cosine distance operator."""
        session = _make_session()

        # Capture the SQL statement passed to session.execute
        captured_stmts: list[Any] = []

        def capture_execute(stmt: Any) -> Any:
            captured_stmts.append(stmt)
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = []
            return result_mock

        session.execute.side_effect = capture_execute

        query_embedding = [0.5] * 384
        retrieve_top_jobs(session, query_embedding, k=5)

        assert len(captured_stmts) == 1, "Expected exactly one session.execute call"
        stmt = captured_stmts[0]

        # Convert to string representation and verify <=> operator is present
        stmt_str = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "<=>" in stmt_str, (
            f"Expected <=> cosine distance operator in query, got: {stmt_str[:500]}"
        )

    def test_retrieve_top_jobs_applies_limit(self) -> None:
        """retrieve_top_jobs must apply a LIMIT clause."""
        session = _make_session()
        captured_stmts: list[Any] = []

        def capture_execute(stmt: Any) -> Any:
            captured_stmts.append(stmt)
            result_mock = MagicMock()
            result_mock.scalars.return_value.all.return_value = []
            return result_mock

        session.execute.side_effect = capture_execute

        retrieve_top_jobs(session, [0.1] * 384, k=7)

        stmt_str = str(captured_stmts[0].compile(compile_kwargs={"literal_binds": True}))
        assert "7" in stmt_str or "LIMIT" in stmt_str.upper(), (
            f"Expected LIMIT in query, got: {stmt_str[:500]}"
        )

    def test_retrieve_top_jobs_returns_domain_objects(self) -> None:
        """retrieve_top_jobs must return a list (may be empty)."""
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        result = retrieve_top_jobs(session, [0.1] * 384, k=10)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# test_get_job_by_id_returns_none_when_missing
# ---------------------------------------------------------------------------


class TestGetJobById:
    def test_get_job_by_id_returns_none_when_missing(self) -> None:
        """get_job_by_id must return None when no row matches the given UUID."""
        session = _make_session()
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = None
        session.scalars.return_value = scalars_mock

        result = get_job_by_id(session, uuid.uuid4())
        assert result is None

    def test_get_job_by_id_returns_job_when_found(self) -> None:
        """get_job_by_id must return a Job domain object when a row is found."""
        from app.types.domain import Job

        session = _make_session()
        row = _make_job_model_row()
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = row
        session.scalars.return_value = scalars_mock

        result = get_job_by_id(session, row.id)
        assert result is not None
        assert isinstance(result, Job)
        assert result.id == row.id
        assert result.title == "Python Developer"


# ---------------------------------------------------------------------------
# test_upsert_job_skips_existing_external_ref
# ---------------------------------------------------------------------------


class TestUpsertJob:
    def test_upsert_job_skips_existing_external_ref(self) -> None:
        """upsert_job must return the existing id without inserting when external_ref exists."""
        session = _make_session()
        existing_id = uuid.uuid4()
        existing_row = _make_job_model_row(job_id=existing_id)

        # Mock SELECT to return existing row
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = existing_row
        session.scalars.return_value = scalars_mock

        record = _make_job_record(external_ref="seed-000001")
        embedding = [0.1] * 384

        result_id = upsert_job(session, record, embedding)

        assert result_id == existing_id, "Should return existing id, not insert a new row"
        session.add.assert_not_called(), "session.add must not be called when row already exists"
        (
            session.flush.assert_not_called(),
            "session.flush must not be called when row already exists",
        )

    def test_upsert_job_inserts_when_no_existing(self) -> None:
        """upsert_job must call session.add and session.flush when external_ref is new."""
        session = _make_session()
        new_id = uuid.uuid4()

        # Mock SELECT returns None (no existing row)
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = None
        session.scalars.return_value = scalars_mock

        # Mock flush to set id on the row
        def mock_flush() -> None:
            # find what was added
            added_row = session.add.call_args[0][0]
            added_row.id = new_id

        session.flush.side_effect = mock_flush

        record = _make_job_record(external_ref="seed-999999")
        embedding = [0.2] * 384

        upsert_job(session, record, embedding)

        session.add.assert_called_once()
        session.flush.assert_called_once()

    def test_upsert_job_with_none_external_ref_always_inserts(self) -> None:
        """upsert_job must always insert when external_ref is None."""
        session = _make_session()
        new_id = uuid.uuid4()

        def mock_flush() -> None:
            added_row = session.add.call_args[0][0]
            added_row.id = new_id

        session.flush.side_effect = mock_flush

        record = _make_job_record(external_ref=None)  # type: ignore[arg-type]
        embedding = [0.3] * 384

        upsert_job(session, record, embedding)

        # Should not query for existing row (no external_ref to look up)
        session.add.assert_called_once()

    def test_upsert_job_never_commits(self) -> None:
        """upsert_job must never call session.commit() — caller owns transaction."""
        session = _make_session()
        scalars_mock = MagicMock()
        scalars_mock.first.return_value = None
        session.scalars.return_value = scalars_mock

        def mock_flush() -> None:
            added_row = session.add.call_args[0][0]
            added_row.id = uuid.uuid4()

        session.flush.side_effect = mock_flush

        record = _make_job_record()
        upsert_job(session, record, [0.1] * 384)

        session.commit.assert_not_called()
        session.rollback.assert_not_called()
        session.close.assert_not_called()


# ---------------------------------------------------------------------------
# test_job_loader_protocol_substitutable
# ---------------------------------------------------------------------------


class TestJobLoaderProtocolSubstitutability:
    def test_job_loader_protocol_substitutable(self) -> None:
        """A stub class implementing JobLoader must satisfy the Protocol via isinstance."""

        class StubJobLoader:
            """Minimal stub satisfying the JobLoader Protocol."""

            def load(self) -> list[JobRecord]:
                return [
                    JobRecord(
                        external_ref="stub-000001",
                        title="Stub Engineer",
                        company="Stub Corp",
                        location="Remote",
                        employment_type="full_time",
                        description="A stub job.",
                        skills=["Python"],
                        seniority="mid",
                        source="seed",
                    )
                ]

        stub = StubJobLoader()
        assert isinstance(stub, JobLoader), (
            "StubJobLoader must satisfy the JobLoader Protocol (runtime_checkable)"
        )

    def test_job_loader_protocol_load_returns_list(self) -> None:
        """A valid JobLoader stub must return a list from load()."""

        class AnotherStub:
            def load(self) -> list[JobRecord]:
                return []

        stub = AnotherStub()
        assert isinstance(stub, JobLoader)
        result = stub.load()
        assert isinstance(result, list)

    def test_class_without_load_not_substitutable(self) -> None:
        """A class without load() must NOT satisfy the JobLoader Protocol."""

        class NotALoader:
            def fetch(self) -> list[JobRecord]:  # wrong method name
                return []

        obj = NotALoader()
        assert not isinstance(obj, JobLoader), (
            "A class without load() should not satisfy JobLoader Protocol"
        )


# ---------------------------------------------------------------------------
# test_get_job_count
# ---------------------------------------------------------------------------


class TestGetJobCount:
    def test_get_job_count_returns_integer(self) -> None:
        """get_job_count must execute a COUNT query and return an integer."""
        session = _make_session()
        execute_result = MagicMock()
        execute_result.scalar_one.return_value = 42
        session.execute.return_value = execute_result

        count = get_job_count(session)
        assert count == 42
        session.execute.assert_called_once()
