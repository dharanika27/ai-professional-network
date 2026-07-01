"""Unit tests for RAGRetrievalService (E5-S3).

All dependencies are mocked — no DB, no model loading, no LLM.

Covers:
  AC-BEHAV-C11: returns k KnowledgeChunks ordered by similarity (repo order preserved)
  AC-BEHAV-C12: empty KB / all-filtered -> RetrievedContext(block='', sources=[])
  AC-BEHAV-C13: k defaults to settings.rag_top_k; caller-supplied k honored
  AC-SCHEMA-C03: Citation carries source_id, source_file, snippet
  AC-IMPORT-C04: rag_retrieval imports no LLM client / provider / groq / fastapi
"""

from __future__ import annotations

import ast
import inspect
import uuid
from datetime import datetime

import pytest

from app.services.ai import rag_retrieval
from app.services.ai.rag_retrieval import RAGRetrievalService, RetrievedContext
from app.types.domain import KnowledgeChunk
from app.types.enums import KnowledgeCategory
from app.types.structured import Citation

# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


class MockEmbeddingProvider:
    """Deterministic fake embedding provider — no model loading."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector if vector is not None else [0.1] * 384
        self.embed_text_calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.embed_text_calls.append(text)
        return list(self._vector)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vector) for _ in texts]


class MockKnowledgeRepository:
    """Records top_k calls and returns a canned list of chunks."""

    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        self._chunks = chunks
        self.top_k_calls: list[dict[str, object]] = []

    def top_k(
        self,
        session: object,
        query_embedding: list[float],
        k: int = 5,
    ) -> list[KnowledgeChunk]:
        self.top_k_calls.append({"session": session, "query_embedding": query_embedding, "k": k})
        return list(self._chunks[:k])


class MockSettings:
    """Minimal stand-in for Settings carrying only the RAG fields."""

    def __init__(self, rag_top_k: int = 5, rag_min_similarity: float = 0.0) -> None:
        self.rag_top_k = rag_top_k
        self.rag_min_similarity = rag_min_similarity


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _make_chunk(
    category: KnowledgeCategory,
    chunk_index: int,
    source_file: str,
    content: str,
    embedding: list[float] | None = None,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=uuid.uuid4(),
        source_file=source_file,
        category=category,
        chunk_index=chunk_index,
        content=content,
        content_hash="0" * 64,
        embedding=embedding if embedding is not None else [0.1] * 384,
        created_at=datetime.now(),
    )


@pytest.fixture()
def two_chunks() -> list[KnowledgeChunk]:
    return [
        _make_chunk(
            KnowledgeCategory.ATS,
            1,
            "ats_best_practices.md",
            "Use standard section headings so ATS parsers can read your resume. " * 10,
        ),
        _make_chunk(
            KnowledgeCategory.RESUME,
            2,
            "resume_writing.md",
            "Lead each bullet with a strong action verb and quantify impact. " * 10,
        ),
    ]


def _service(
    chunks: list[KnowledgeChunk],
    *,
    rag_top_k: int = 5,
    rag_min_similarity: float = 0.0,
    query_vector: list[float] | None = None,
) -> tuple[RAGRetrievalService, MockEmbeddingProvider, MockKnowledgeRepository]:
    provider = MockEmbeddingProvider(vector=query_vector)
    repo = MockKnowledgeRepository(chunks)
    settings = MockSettings(rag_top_k=rag_top_k, rag_min_similarity=rag_min_similarity)
    svc = RAGRetrievalService(
        embedding_provider=provider,
        knowledge_repo=repo,
        settings=settings,
    )
    return svc, provider, repo


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_happy_path_returns_block_and_two_citations(
    two_chunks: list[KnowledgeChunk],
) -> None:
    svc, provider, repo = _service(two_chunks)

    result = svc.retrieve("How do I pass ATS?", session=object())

    assert isinstance(result, RetrievedContext)
    assert result.block  # non-empty
    assert len(result.sources) == 2

    # source_id = f"{category}-{chunk_index}"
    assert result.sources[0].source_id == "ats-1"
    assert result.sources[1].source_id == "resume-2"

    # block references the citation handles
    assert "[ats-1]" in result.block
    assert "[resume-2]" in result.block

    # citations carry file + snippet
    for citation in result.sources:
        assert isinstance(citation, Citation)
        assert citation.source_file
        assert citation.snippet


def test_query_is_embedded_once(two_chunks: list[KnowledgeChunk]) -> None:
    svc, provider, repo = _service(two_chunks)
    svc.retrieve("optimize resume", session=object())
    assert provider.embed_text_calls == ["optimize resume"]


def test_repo_receives_embedded_query(two_chunks: list[KnowledgeChunk]) -> None:
    query_vector = [0.2] * 384
    svc, provider, repo = _service(two_chunks, query_vector=query_vector)
    svc.retrieve("q", session=object())
    assert repo.top_k_calls[0]["query_embedding"] == query_vector


# ---------------------------------------------------------------------------
# 2. Empty KB
# ---------------------------------------------------------------------------


def test_empty_kb_returns_empty_context() -> None:
    svc, provider, repo = _service([])

    result = svc.retrieve("anything", session=object())

    assert result.block == ""
    assert result.sources == []


# ---------------------------------------------------------------------------
# 3. Similarity floor filters everything out
# ---------------------------------------------------------------------------


def test_similarity_floor_filters_all(two_chunks: list[KnowledgeChunk]) -> None:
    # A floor above the max possible cosine similarity (1.0) removes every chunk.
    svc, provider, repo = _service(two_chunks, rag_min_similarity=1.1)

    result = svc.retrieve("anything", session=object())

    assert result.block == ""
    assert result.sources == []


def test_similarity_floor_zero_returns_all(two_chunks: list[KnowledgeChunk]) -> None:
    svc, provider, repo = _service(two_chunks, rag_min_similarity=0.0)
    result = svc.retrieve("anything", session=object())
    assert len(result.sources) == 2


def test_similarity_floor_partial_filter() -> None:
    # Query aligned with chunk A's embedding; chunk B is orthogonal.
    vec_a = [1.0] + [0.0] * 383
    vec_b = [0.0, 1.0] + [0.0] * 382
    chunks = [
        _make_chunk(KnowledgeCategory.ATS, 1, "a.md", "aaa " * 60, embedding=vec_a),
        _make_chunk(KnowledgeCategory.RESUME, 2, "b.md", "bbb " * 60, embedding=vec_b),
    ]
    # Floor of 0.5 keeps A (sim=1.0) and drops B (sim=0.0).
    svc, provider, repo = _service(chunks, rag_min_similarity=0.5, query_vector=vec_a)
    result = svc.retrieve("q", session=object())
    assert len(result.sources) == 1
    assert result.sources[0].source_id == "ats-1"


# ---------------------------------------------------------------------------
# 4 & 5. k defaulting and explicit k
# ---------------------------------------------------------------------------


def test_k_defaults_to_settings(two_chunks: list[KnowledgeChunk]) -> None:
    svc, provider, repo = _service(two_chunks, rag_top_k=5)
    svc.retrieve("q", session=object())
    assert repo.top_k_calls[0]["k"] == 5


def test_explicit_k_is_honored(two_chunks: list[KnowledgeChunk]) -> None:
    svc, provider, repo = _service(two_chunks, rag_top_k=5)
    svc.retrieve("q", k=3, session=object())
    assert repo.top_k_calls[0]["k"] == 3


# ---------------------------------------------------------------------------
# 6. No LLM / fastapi import (AC-IMPORT-C04)
# ---------------------------------------------------------------------------


def test_no_llm_or_fastapi_import() -> None:
    # Parse the module source and inspect actual import statements, so that the
    # forbidden names appearing in prose (docstrings/comments) do not false-fail.
    tree = ast.parse(inspect.getsource(rag_retrieval))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)

    forbidden = ["llm_client", "llm_provider", "groq_provider", "groq", "fastapi"]
    for module in imported:
        for token in forbidden:
            assert token not in module, (
                f"rag_retrieval must not import {token!r} (found in {module!r})"
            )


# ---------------------------------------------------------------------------
# 7. Citation schema (AC-SCHEMA-C03)
# ---------------------------------------------------------------------------


def test_citation_has_expected_fields() -> None:
    fields = set(Citation.model_fields.keys())
    assert {"source_id", "source_file", "snippet"} <= fields


# ---------------------------------------------------------------------------
# 8. source_id format
# ---------------------------------------------------------------------------


def test_source_id_format() -> None:
    chunk = _make_chunk(KnowledgeCategory.ATS, 1, "ats_best_practices.md", "x" * 300)
    svc, provider, repo = _service([chunk])
    result = svc.retrieve("q", session=object())
    assert result.sources[0].source_id == "ats-1"


def test_snippet_is_first_200_chars() -> None:
    long_content = "z" * 500
    chunk = _make_chunk(KnowledgeCategory.CAREER, 7, "career_guidance.md", long_content)
    svc, provider, repo = _service([chunk])
    result = svc.retrieve("q", session=object())
    assert result.sources[0].snippet == "z" * 200
    assert result.sources[0].source_id == "career-7"


# ---------------------------------------------------------------------------
# 9. Zero-magnitude vector in cosine similarity (_cosine_similarity edge case)
# ---------------------------------------------------------------------------


def test_zero_vector_similarity_returns_zero() -> None:
    """A zero-magnitude query vector returns 0.0 similarity (no error)."""
    from app.services.ai.rag_retrieval import _cosine_similarity

    zero = [0.0] * 384
    nonzero = [0.1] * 384
    assert _cosine_similarity(zero, nonzero) == 0.0
    assert _cosine_similarity(nonzero, zero) == 0.0
    assert _cosine_similarity(zero, zero) == 0.0
