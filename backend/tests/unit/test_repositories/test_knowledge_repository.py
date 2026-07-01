"""Unit tests for knowledge_repository (E5-S2).

Tests written FIRST (TDD). Uses mock sessions — no live DB required.
Verifies cosine query shape, chunk_exists logic, and get_chunk_count.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock

from app.repositories.knowledge_repository import KnowledgeRepository
from app.types.domain import KnowledgeChunk
from app.types.enums import KnowledgeCategory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_embedding(dim: int = 384) -> list[float]:
    """Return a zero-padded unit-like fake embedding."""
    vec = [0.0] * dim
    vec[0] = 1.0
    return vec


def _fake_chunk_row() -> MagicMock:
    """Return a MagicMock that looks like a KnowledgeChunkModel row."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.source_file = "ats_best_practices.md"
    row.category = "ats"
    row.chunk_index = 0
    row.content = "ATS parsing best practices content for testing purposes."
    row.content_hash = "abc123def456" * 5
    row.embedding = _fake_embedding()
    row.created_at = datetime(2024, 1, 15, 10, 30, 0)
    return row


# ---------------------------------------------------------------------------
# test_top_k_executes_cosine_query
# ---------------------------------------------------------------------------


def test_top_k_executes_cosine_query() -> None:
    """top_k must issue a query that orders by pgvector <=> cosine distance."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    row = _fake_chunk_row()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    mock_session.execute.return_value = mock_result

    query_embedding = _fake_embedding()
    repo.top_k(session=mock_session, query_embedding=query_embedding, k=5)

    # Session.execute must have been called exactly once
    mock_session.execute.assert_called_once()

    # Extract the statement that was passed
    stmt = mock_session.execute.call_args[0][0]

    # The statement should compile to SQL containing <=> operator
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "<=>" in compiled, f"Expected <=> in query, got: {compiled}"
    assert "LIMIT" in compiled.upper() or "limit" in compiled, (
        "Expected LIMIT clause in cosine query"
    )


def test_top_k_returns_domain_objects() -> None:
    """top_k must return list[KnowledgeChunk] domain objects."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    row = _fake_chunk_row()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row]
    mock_session.execute.return_value = mock_result

    results = repo.top_k(session=mock_session, query_embedding=_fake_embedding(), k=5)

    assert isinstance(results, list)
    assert len(results) == 1
    item = results[0]
    assert isinstance(item, KnowledgeChunk)
    assert item.source_file == "ats_best_practices.md"
    assert item.category == KnowledgeCategory.ATS
    assert item.chunk_index == 0


def test_top_k_returns_empty_list_when_no_results() -> None:
    """top_k must return [] when the DB has no matching rows."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    results = repo.top_k(session=mock_session, query_embedding=_fake_embedding(), k=5)

    assert results == []


# ---------------------------------------------------------------------------
# test_chunk_exists_true_when_found
# ---------------------------------------------------------------------------


def test_chunk_exists_true_when_found() -> None:
    """chunk_exists must return True when a row with the hash is found."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    mock_scalar = MagicMock()
    mock_scalar.first.return_value = MagicMock()  # non-None → exists
    mock_session.scalars.return_value = mock_scalar

    result = repo.chunk_exists(session=mock_session, content_hash="deadbeef" * 8)

    assert result is True
    mock_session.scalars.assert_called_once()


# ---------------------------------------------------------------------------
# test_chunk_exists_false_when_not_found
# ---------------------------------------------------------------------------


def test_chunk_exists_false_when_not_found() -> None:
    """chunk_exists must return False when no row matches the hash."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    mock_scalar = MagicMock()
    mock_scalar.first.return_value = None  # None → does not exist
    mock_session.scalars.return_value = mock_scalar

    result = repo.chunk_exists(session=mock_session, content_hash="cafebabe" * 8)

    assert result is False
    mock_session.scalars.assert_called_once()


# ---------------------------------------------------------------------------
# test_get_chunk_count
# ---------------------------------------------------------------------------


def test_get_chunk_count_returns_integer() -> None:
    """get_chunk_count must return an int representing total row count."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    mock_session.execute.return_value.scalar_one.return_value = 42

    count = repo.get_chunk_count(session=mock_session)

    assert count == 42
    assert isinstance(count, int)


def test_get_chunk_count_returns_zero_for_empty_table() -> None:
    """get_chunk_count returns 0 when table has no rows."""
    repo = KnowledgeRepository()
    mock_session = MagicMock()

    mock_session.execute.return_value.scalar_one.return_value = 0

    count = repo.get_chunk_count(session=mock_session)

    assert count == 0


# ---------------------------------------------------------------------------
# test_upsert_chunk
# ---------------------------------------------------------------------------


def test_upsert_chunk_adds_to_session() -> None:
    """upsert_chunk must call session.execute with an INSERT statement."""
    from app.db.models import KnowledgeChunkModel

    repo = KnowledgeRepository()
    mock_session = MagicMock()

    chunk = KnowledgeChunkModel(
        source_file="career_guidance.md",
        category="career",
        chunk_index=0,
        content="Career guidance content for unit test.",
        content_hash="a" * 64,
        embedding=_fake_embedding(),
    )

    repo.upsert_chunk(session=mock_session, chunk=chunk)

    # Must have called session.execute (INSERT ON CONFLICT DO NOTHING)
    mock_session.execute.assert_called_once()
