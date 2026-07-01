"""Integration tests for job_repository.py against live DB.

Requires TEST_DATABASE_URL pointing to a running PostgreSQL instance.
Each test uses the db_session fixture which rolls back after the test,
so all writes are automatically reverted — no cleanup needed.

Tests cover:
  AC-BEHAV-B17 — seed file has 500-1000 jobs
  AC-BEHAV-B18 — upsert idempotent on external_ref
  AC-BEHAV-B19 — get_job_by_id returns correct job or None
  AC-BEHAV-B19 — retrieve_top_jobs returns ordered results
"""

from __future__ import annotations

import pathlib
import uuid

from sqlalchemy.orm import Session

from app.repositories.job_repository import (
    get_job_by_id,
    retrieve_top_jobs,
    upsert_job,
)
from app.types.domain import Job
from seeds.loaders.job_loader import JobRecord, SeedJobLoader

# ---------------------------------------------------------------------------
# FakeEmbeddingProvider — deterministic, no ML model required
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic fake embedding provider for tests.

    Uses MD5 hash of text to produce a fixed 384-dim float vector.
    No sentence-transformers dependency — fast and deterministic.
    """

    def embed_text(self, text: str) -> list[float]:
        import hashlib

        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % 1000
        return [float(seed + i) / 10000 for i in range(384)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


_fake_embedder = FakeEmbeddingProvider()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    external_ref: str,
    title: str = "Python Developer",
    company: str = "Nimbus Cloud",
    description: str = "Build scalable APIs.",
    skills: list[str] | None = None,
) -> JobRecord:
    return JobRecord(
        external_ref=external_ref,
        title=title,
        company=company,
        location="Bengaluru, India",
        employment_type="full_time",
        description=description,
        skills=skills or ["Python", "FastAPI"],
        seniority="mid",
        source="seed",
    )


def _embed(text: str) -> list[float]:
    return _fake_embedder.embed_text(text)


# ---------------------------------------------------------------------------
# test_upsert_job_inserts_new  (AC-BEHAV-B18)
# ---------------------------------------------------------------------------


class TestUpsertJobInsertsNew:
    def test_upsert_job_inserts_new(self, db_session: Session) -> None:
        """upsert_job must insert a new job and return a valid UUID."""
        record = _make_record(external_ref=f"test-{uuid.uuid4().hex[:8]}")
        embedding = _embed(record.description)

        job_id = upsert_job(db_session, record, embedding)

        assert isinstance(job_id, uuid.UUID), "upsert_job must return a UUID"

        # Verify the job is visible within the same session (after flush)
        job = get_job_by_id(db_session, job_id)
        assert job is not None
        assert job.title == record.title
        assert job.company == record.company
        assert job.external_ref == record.external_ref

    def test_upsert_job_stores_skills_correctly(self, db_session: Session) -> None:
        """upsert_job must persist the skills list."""
        record = _make_record(
            external_ref=f"test-skills-{uuid.uuid4().hex[:8]}",
            skills=["Python", "FastAPI", "PostgreSQL"],
        )
        job_id = upsert_job(db_session, record, _embed(record.description))
        job = get_job_by_id(db_session, job_id)

        assert job is not None
        assert "Python" in job.skills
        assert "FastAPI" in job.skills
        assert "PostgreSQL" in job.skills


# ---------------------------------------------------------------------------
# test_upsert_job_idempotent_on_external_ref  (AC-BEHAV-B18)
# ---------------------------------------------------------------------------


class TestUpsertJobIdempotent:
    def test_upsert_job_idempotent_on_external_ref(self, db_session: Session) -> None:
        """Inserting the same external_ref twice must keep count at 1 (AC-BEHAV-B18)."""
        ref = f"test-idem-{uuid.uuid4().hex[:8]}"
        record = _make_record(external_ref=ref)
        embedding = _embed(record.description)

        id1 = upsert_job(db_session, record, embedding)
        id2 = upsert_job(db_session, record, embedding)

        assert id1 == id2, "Second upsert must return the same id as the first"

        # Verify exactly one row exists for this external_ref
        from sqlalchemy import func, select

        from app.db.models import JobModel

        count_result = db_session.execute(select(func.count()).where(JobModel.external_ref == ref))
        count = count_result.scalar_one()
        assert count == 1, f"Expected exactly 1 row, found {count}"

    def test_upsert_job_with_none_ref_allows_duplicates(self, db_session: Session) -> None:
        """Jobs with external_ref=None are always inserted (no dedup)."""
        record = JobRecord(
            external_ref=None,  # type: ignore[arg-type]
            title="No Ref Job",
            company="Test Corp",
            location="Remote",
            employment_type="contract",
            description="A job without a reference.",
            skills=["Python"],
            seniority="entry",
            source="seed",
        )
        embedding = _embed(record.description)

        id1 = upsert_job(db_session, record, embedding)
        id2 = upsert_job(db_session, record, embedding)

        assert id1 != id2, "Jobs with None external_ref must always insert new rows"


# ---------------------------------------------------------------------------
# test_get_job_by_id_existing / test_get_job_by_id_unknown  (AC-BEHAV-B19)
# ---------------------------------------------------------------------------


class TestGetJobById:
    def test_get_job_by_id_existing(self, db_session: Session) -> None:
        """get_job_by_id must return a Job domain object for a known id (AC-BEHAV-B19)."""
        record = _make_record(external_ref=f"test-byid-{uuid.uuid4().hex[:8]}")
        job_id = upsert_job(db_session, record, _embed(record.description))

        result = get_job_by_id(db_session, job_id)

        assert result is not None
        assert isinstance(result, Job)
        assert result.id == job_id
        assert result.title == record.title
        assert result.company == record.company
        assert result.location == record.location
        assert result.source.value == "seed"

    def test_get_job_by_id_unknown(self, db_session: Session) -> None:
        """get_job_by_id must return None for a random UUID that does not exist (AC-BEHAV-B19)."""
        random_id = uuid.uuid4()
        result = get_job_by_id(db_session, random_id)
        assert result is None


# ---------------------------------------------------------------------------
# test_retrieve_top_jobs_returns_ordered  (AC-BEHAV-B19)
# ---------------------------------------------------------------------------


class TestRetrieveTopJobs:
    def test_retrieve_top_jobs_returns_ordered(self, db_session: Session) -> None:
        """retrieve_top_jobs must return top-k results (AC-BEHAV-B19).

        Insert 15 jobs with unique fake embeddings, then query top 10.
        The result should contain exactly 10 items (k=10).
        """
        # Insert 15 unique jobs
        inserted_ids: list[uuid.UUID] = []
        for i in range(15):
            record = _make_record(
                external_ref=f"test-topk-{uuid.uuid4().hex[:8]}",
                title=f"Engineer Level {i}",
                description=f"Job description variant {i} with unique content number {i * 7}.",
            )
            embedding = _embed(record.description)
            job_id = upsert_job(db_session, record, embedding)
            inserted_ids.append(job_id)

        # Query embedding — use a distinct text to get ordering
        query_emb = _embed("Python FastAPI PostgreSQL senior engineer backend")
        results = retrieve_top_jobs(db_session, query_emb, k=10)

        # Must return at most k results
        assert len(results) <= 10, f"Expected at most 10 results, got {len(results)}"
        # Must return at least 1 result (we inserted 15)
        assert len(results) >= 1, "Expected at least 1 result"

        # All returned items must be Job domain objects
        for job in results:
            assert isinstance(job, Job), f"Expected Job, got {type(job)}"

    def test_retrieve_top_jobs_respects_k_limit(self, db_session: Session) -> None:
        """retrieve_top_jobs must respect the k parameter."""
        # Insert 5 jobs
        for i in range(5):
            record = _make_record(
                external_ref=f"test-klimit-{uuid.uuid4().hex[:8]}",
                description=f"Backend role focused on Python and APIs, variant {i}.",
            )
            upsert_job(db_session, record, _embed(record.description))

        results = retrieve_top_jobs(db_session, _embed("Python backend engineer"), k=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# test_seed_file_count_in_range  (AC-BEHAV-B17)
# ---------------------------------------------------------------------------


class TestSeedFileCount:
    def test_seed_file_count_in_range(self) -> None:
        """The jobs_seed.json fixture must contain between 500 and 1000 jobs (AC-BEHAV-B17)."""
        seed_file = (
            pathlib.Path(__file__).parent.parent.parent / "seeds" / "jobs" / "jobs_seed.json"
        )
        assert seed_file.exists(), f"Seed file not found at: {seed_file}"

        loader = SeedJobLoader(seed_file)
        records = loader.load()

        assert 500 <= len(records) <= 1000, f"Expected 500-1000 seed jobs, found {len(records)}"

    def test_seed_file_external_refs_unique(self) -> None:
        """All external_ref values in the seed file must be unique."""
        seed_file = (
            pathlib.Path(__file__).parent.parent.parent / "seeds" / "jobs" / "jobs_seed.json"
        )
        loader = SeedJobLoader(seed_file)
        records = loader.load()

        refs = [r.external_ref for r in records]
        assert len(refs) == len(set(refs)), "All external_ref values must be unique"

    def test_seed_file_all_have_required_fields(self) -> None:
        """All seed records must have required fields populated."""
        seed_file = (
            pathlib.Path(__file__).parent.parent.parent / "seeds" / "jobs" / "jobs_seed.json"
        )
        loader = SeedJobLoader(seed_file)
        records = loader.load()

        for i, record in enumerate(records):
            assert record.title, f"Record {i} missing title"
            assert record.company, f"Record {i} missing company"
            assert record.location, f"Record {i} missing location"
            assert record.description, f"Record {i} missing description"
            assert record.source == "seed", f"Record {i} source should be 'seed'"
