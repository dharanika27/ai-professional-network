"""Integration tests for KB ingestion (E5-S2).

Tests run against a live test DB using db_session fixture from conftest.py.
Uses FakeEmbeddingProvider to avoid loading the bge-small model — all
embeddings live in the same fake space so cosine queries are still valid.

AC-BEHAV-B14: ingest creates chunks with correct attribution fields
AC-BEHAV-B15: ingest is idempotent (run twice, count unchanged)
AC-BEHAV-B16: top_k returns ordered results after ingest
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest
from sqlalchemy.orm import Session

from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.ai.kb_ingestion import ingest_kb

KB_DIR = pathlib.Path(__file__).parent.parent.parent / "kb"

VALID_CATEGORIES = {"ats", "resume", "profile", "interview", "career"}


# ---------------------------------------------------------------------------
# Fake embedding provider — no model loading, deterministic
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Fast deterministic embedding provider for integration tests."""

    def embed_text(self, text: str) -> list[float]:
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % 1000
        return [float(seed + i) / 10000 for i in range(384)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture()
def knowledge_repo() -> KnowledgeRepository:
    return KnowledgeRepository()


@pytest.fixture(autouse=True)
def clean_knowledge_chunks(db_session: Session) -> None:
    """Delete all knowledge_chunk rows before each test for isolation."""
    from app.db.models import KnowledgeChunkModel

    db_session.execute(__import__("sqlalchemy").delete(KnowledgeChunkModel))
    db_session.flush()


# ---------------------------------------------------------------------------
# AC-BEHAV-B14: ingest creates chunks with correct attribution
# ---------------------------------------------------------------------------


def test_ingest_kb_creates_chunks_with_attribution(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    """Ingested chunks must have correct source_file, category, content_hash, embedding dim."""
    result = ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )
    db_session.flush()

    total_inserted = sum(result.values())
    assert total_inserted > 0, "Expected at least one chunk to be inserted"

    import sqlalchemy as sa

    from app.db.models import KnowledgeChunkModel

    rows = db_session.execute(sa.select(KnowledgeChunkModel)).scalars().all()
    assert len(rows) == total_inserted

    for row in rows:
        # source_file is filename only (no path)
        assert "/" not in row.source_file, f"source_file should be filename only: {row.source_file}"
        assert row.source_file.endswith(".md"), f"source_file must end with .md: {row.source_file}"

        # category must be a valid value
        assert row.category in VALID_CATEGORIES, f"Invalid category: {row.category}"

        # content_hash must equal sha256(content)
        expected_hash = hashlib.sha256(row.content.encode()).hexdigest()
        assert row.content_hash == expected_hash, (
            f"content_hash mismatch for chunk {row.chunk_index} in {row.source_file}"
        )

        # embedding must be 384-dimensional
        assert row.embedding is not None, "embedding must not be None"
        assert len(row.embedding) == 384, (
            f"Expected embedding dim=384, got {len(row.embedding)} for {row.source_file}"
        )


# ---------------------------------------------------------------------------
# AC-BEHAV-B15: ingest is idempotent
# ---------------------------------------------------------------------------


def test_ingest_kb_idempotent(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    """Running ingest twice must not increase the chunk count."""
    ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )
    db_session.flush()

    count_after_first = knowledge_repo.get_chunk_count(session=db_session)
    assert count_after_first > 0, "First ingest must create chunks"

    second_result = ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )
    db_session.flush()

    count_after_second = knowledge_repo.get_chunk_count(session=db_session)
    assert count_after_second == count_after_first, (
        f"Second ingest must not increase count: "
        f"before={count_after_first}, after={count_after_second}"
    )

    total_second_inserted = sum(second_result.values())
    assert total_second_inserted == 0, (
        f"Second ingest must insert 0 new chunks, inserted {total_second_inserted}"
    )


# ---------------------------------------------------------------------------
# AC-BEHAV-B16: top_k returns ordered results after ingest
# ---------------------------------------------------------------------------


def test_top_k_returns_ordered_results(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    """After ingest, top_k must return up to k results."""
    ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )
    db_session.flush()

    query_embedding = fake_provider.embed_text("How do I optimize my resume for ATS?")
    results = knowledge_repo.top_k(
        session=db_session,
        query_embedding=query_embedding,
        k=5,
    )

    assert len(results) == 5, f"Expected 5 results, got {len(results)}"

    from app.types.domain import KnowledgeChunk

    for item in results:
        assert isinstance(item, KnowledgeChunk)
        assert item.source_file
        assert item.content
        assert item.category in {c for c in VALID_CATEGORIES}


# ---------------------------------------------------------------------------
# test_chunk_embedding_dim_is_384
# ---------------------------------------------------------------------------


def test_chunk_embedding_dim_is_384(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    """All stored embeddings must have exactly 384 dimensions."""
    ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )
    db_session.flush()

    import sqlalchemy as sa

    from app.db.models import KnowledgeChunkModel

    rows = db_session.execute(sa.select(KnowledgeChunkModel)).scalars().all()
    assert len(rows) > 0

    for row in rows:
        assert len(row.embedding) == 384, (
            f"Embedding dim must be 384, got {len(row.embedding)} "
            f"for {row.source_file} chunk {row.chunk_index}"
        )


# ---------------------------------------------------------------------------
# test_chunk_category_in_valid_set
# ---------------------------------------------------------------------------


def test_chunk_category_in_valid_set(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    """Every ingested chunk must have a category in the valid set."""
    ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )
    db_session.flush()

    import sqlalchemy as sa

    from app.db.models import KnowledgeChunkModel

    rows = db_session.execute(sa.select(KnowledgeChunkModel)).scalars().all()
    assert len(rows) > 0

    for row in rows:
        assert row.category in VALID_CATEGORIES, (
            f"Unexpected category={row.category!r} for file={row.source_file}"
        )


# ---------------------------------------------------------------------------
# test_ingest_covers_all_five_files
# ---------------------------------------------------------------------------


def test_ingest_covers_all_five_files(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    """ingest_kb must process all five KB markdown files."""
    result = ingest_kb(
        session=db_session,
        provider=fake_provider,
        kb_dir=KB_DIR,
        knowledge_repo=knowledge_repo,
    )

    expected_files = {
        "ats_best_practices.md",
        "resume_writing.md",
        "profile_optimization.md",
        "interview_prep.md",
        "career_guidance.md",
    }
    assert set(result.keys()) == expected_files, (
        f"Expected files {expected_files}, got {set(result.keys())}"
    )
    for filename, count in result.items():
        assert count > 0, f"File {filename} produced 0 chunks"
