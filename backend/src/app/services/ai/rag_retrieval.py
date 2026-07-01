"""RAG retrieval service (E5-S3) — embed query, top-k KB search, assemble context.

This service performs NO LLM call. It only:
  1. Embeds the query text via an EmbeddingProvider.
  2. Retrieves the top-k nearest KnowledgeChunks via KnowledgeRepository.top_k.
  3. Optionally applies a cosine-similarity floor.
  4. Assembles a grounding context block and a list of Citations.

CRITICAL (AC-IMPORT-C04):
  - No LLM client or provider imports. No external AI-SDK imports. No fastapi import.
  - This is a retrieval-only, provider-agnostic service.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.types.structured import Citation

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.config.settings import Settings
    from app.repositories.knowledge_repository import KnowledgeRepository
    from app.services.ai.embedding_provider import EmbeddingProvider
    from app.types.domain import KnowledgeChunk

logger = logging.getLogger(__name__)

# Number of leading content characters used for both the snippet and block body.
_SNIPPET_CHARS = 200


class _EmbeddingProvider(Protocol):
    """Structural interface — avoids a hard import of the concrete provider."""

    def embed_text(self, text: str) -> list[float]: ...


@dataclass
class RetrievedContext:
    """Result of a retrieval call.

    block:   grounding text block ("" if nothing retrieved).
    sources: list of citations ([] if nothing retrieved).
    """

    block: str
    sources: list[Citation]


class RAGRetrievalService:
    """Embeds a query and retrieves grounding context from the knowledge base."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        knowledge_repo: KnowledgeRepository,
        settings: Settings,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._knowledge_repo = knowledge_repo
        self._settings = settings

    def retrieve(
        self,
        query_text: str,
        *,
        session: Session,
        k: int | None = None,
    ) -> RetrievedContext:
        """Embed the query, retrieve top-k chunks, assemble context + citations.

        AC-BEHAV-C11: returns k KnowledgeChunks ordered by similarity (repo order).
        AC-BEHAV-C12: returns RetrievedContext(block='', sources=[]) when the KB is
                      empty or no chunk passes the similarity floor.
        AC-BEHAV-C13: k defaults to settings.rag_top_k; a caller-supplied k is honored.
        """
        effective_k = k if k is not None else self._settings.rag_top_k

        query_embedding = self._embedding_provider.embed_text(query_text)
        chunks = self._knowledge_repo.top_k(
            session=session,
            query_embedding=query_embedding,
            k=effective_k,
        )

        floor = self._settings.rag_min_similarity
        if floor > 0.0:
            chunks = [
                chunk
                for chunk in chunks
                if _cosine_similarity(query_embedding, chunk.embedding) >= floor
            ]

        logger.debug(
            "rag retrieve completed",
            extra={"k": effective_k, "chunks_returned": len(chunks), "floor": floor},
        )

        if not chunks:
            return RetrievedContext(block="", sources=[])

        citations = [_to_citation(chunk) for chunk in chunks]
        block = _assemble_block(chunks, citations)
        return RetrievedContext(block=block, sources=citations)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_citation(chunk: KnowledgeChunk) -> Citation:
    """Build a Citation with a stable source_id and a leading-content snippet."""
    return Citation(
        source_id=f"{chunk.category}-{chunk.chunk_index}",
        source_file=chunk.source_file,
        snippet=chunk.content[:_SNIPPET_CHARS],
    )


def _assemble_block(
    chunks: list[KnowledgeChunk],
    citations: list[Citation],
) -> str:
    """Join chunks into a grounding block: '[source_id] (source_file) snippet'."""
    lines = [
        f"[{citation.source_id}] ({citation.source_file}) {chunk.content[:_SNIPPET_CHARS]}"
        for chunk, citation in zip(chunks, citations, strict=True)
    ]
    return "\n".join(lines)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors; 0.0 if either has zero magnitude."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)
