"""Integration tests for RAGRetrievalService (E5-S3) against a live DB.

Inserts KnowledgeChunk rows via the real KnowledgeRepository, then exercises
RAGRetrievalService.retrieve with a deterministic fake embedding provider so
no model is loaded. Uses the db_session fixture from tests/conftest.py.

AC-BEHAV-C11: retrieve returns top-k chunks (repo order preserved)
AC-BEHAV-C12: empty DB -> RetrievedContext(block='', sources=[])
AC-SCHEMA-C03: sources are schema-valid Citations
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.models import KnowledgeChunkModel
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.ai.rag_retrieval import RAGRetrievalService, RetrievedContext
from app.types.domain import KnowledgeChunk
from app.types.enums import KnowledgeCategory
from app.types.structured import Citation

# ---------------------------------------------------------------------------
# Deterministic fake embedding provider (same space for all vectors)
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Fast deterministic embedding provider for integration tests."""

    def embed_text(self, text: str) -> list[float]:
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % 1000
        return [float(seed + i) / 10000 for i in range(384)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


class _Settings:
    """Minimal settings carrying only the RAG fields the service reads."""

    def __init__(self, rag_top_k: int = 5, rag_min_similarity: float = 0.0) -> None:
        self.rag_top_k = rag_top_k
        self.rag_min_similarity = rag_min_similarity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture()
def knowledge_repo() -> KnowledgeRepository:
    return KnowledgeRepository()


@pytest.fixture(autouse=True)
def clean_knowledge_chunks(db_session: Session) -> None:
    """Isolate each test — delete all knowledge_chunk rows first."""
    db_session.execute(sa.delete(KnowledgeChunkModel))
    db_session.flush()


def _seed(
    db_session: Session,
    knowledge_repo: KnowledgeRepository,
    provider: FakeEmbeddingProvider,
) -> int:
    """Insert three chunks across categories; return the count inserted."""
    specs = [
        (
            KnowledgeCategory.ATS,
            1,
            "ats_best_practices.md",
            "Use standard headings so ATS parsers read your resume correctly. " * 8,
        ),
        (
            KnowledgeCategory.RESUME,
            2,
            "resume_writing.md",
            "Start each bullet with an action verb and quantify the impact. " * 8,
        ),
        (
            KnowledgeCategory.INTERVIEW,
            3,
            "interview_prep.md",
            "Practice the STAR method for behavioral interview questions. " * 8,
        ),
    ]
    for category, idx, source_file, content in specs:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        chunk = KnowledgeChunk(
            id=uuid.uuid4(),
            source_file=source_file,
            category=category,
            chunk_index=idx,
            content=content,
            content_hash=content_hash,
            embedding=provider.embed_text(content),
            created_at=datetime.now(),
        )
        knowledge_repo.upsert_chunk(session=db_session, chunk=chunk)
    db_session.flush()
    return len(specs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_retrieve_returns_topk_valid_citations(
    db_session: Session,
    provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    inserted = _seed(db_session, knowledge_repo, provider)

    svc = RAGRetrievalService(
        embedding_provider=provider,
        knowledge_repo=knowledge_repo,
        settings=_Settings(rag_top_k=5),
    )
    result = svc.retrieve("How do I optimize my resume for ATS?", session=db_session)

    assert isinstance(result, RetrievedContext)
    assert result.block
    assert 0 < len(result.sources) <= inserted

    for citation in result.sources:
        assert isinstance(citation, Citation)
        assert citation.source_id
        assert "-" in citation.source_id
        assert citation.source_file.endswith(".md")
        assert citation.snippet
        # snippet is echoed inside the block under its source_id handle
        assert f"[{citation.source_id}]" in result.block


def test_retrieve_honors_explicit_k(
    db_session: Session,
    provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    _seed(db_session, knowledge_repo, provider)

    svc = RAGRetrievalService(
        embedding_provider=provider,
        knowledge_repo=knowledge_repo,
        settings=_Settings(rag_top_k=5),
    )
    result = svc.retrieve("resume tips", k=2, session=db_session)
    assert len(result.sources) == 2


def test_retrieve_empty_db_returns_empty_context(
    db_session: Session,
    provider: FakeEmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
) -> None:
    # clean_knowledge_chunks already emptied the table; do not seed.
    svc = RAGRetrievalService(
        embedding_provider=provider,
        knowledge_repo=knowledge_repo,
        settings=_Settings(),
    )
    result = svc.retrieve("anything at all", session=db_session)

    assert isinstance(result, RetrievedContext)
    assert result.block == ""
    assert result.sources == []
