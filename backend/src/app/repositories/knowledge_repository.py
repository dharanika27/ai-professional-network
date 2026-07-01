"""Knowledge chunk repository — pgvector cosine search and idempotent upsert.

Implements:
  - upsert_chunk  — INSERT ON CONFLICT DO NOTHING (idempotent)
  - top_k         — cosine similarity search via pgvector <=> operator
  - get_chunk_count — total row count
  - chunk_exists  — hash-based existence check

CRITICAL:
  - NEVER import EmbeddingProvider, sentence_transformers, or any LLM client here
  - NEVER call session.commit(), session.rollback(), or session.close()
  - NEVER import from app.services or app.api
  - Query embedding is passed as list[float] — this repo never calls any provider
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import KnowledgeChunkModel
from app.types.domain import KnowledgeChunk
from app.types.enums import KnowledgeCategory

logger = logging.getLogger(__name__)


class KnowledgeRepository:
    """Repository for knowledge_chunks table operations."""

    def upsert_chunk(self, session: Session, chunk: KnowledgeChunkModel) -> None:
        """Insert a KnowledgeChunk row if content_hash not already present.

        Uses INSERT ... ON CONFLICT (content_hash) DO NOTHING for idempotency.
        Transaction boundary: caller owns commit/rollback.
        """
        stmt = (
            pg_insert(KnowledgeChunkModel)
            .values(
                id=chunk.id if chunk.id is not None else uuid.uuid4(),
                source_file=chunk.source_file,
                category=chunk.category,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                embedding=chunk.embedding,
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
        )
        session.execute(stmt)
        logger.debug(
            "upsert_chunk executed",
            extra={
                "source_file": chunk.source_file,
                "chunk_index": chunk.chunk_index,
                "content_hash": chunk.content_hash[:16],
            },
        )

    def top_k(
        self,
        session: Session,
        query_embedding: list[float],
        k: int = 5,
    ) -> list[KnowledgeChunk]:
        """Return top-k KnowledgeChunks ordered by cosine similarity.

        Uses pgvector cosine distance operator <=> for ordering.
        The query_embedding is passed in — this repo never calls EmbeddingProvider.

        Returns domain KnowledgeChunk objects with all citation fields populated.
        """
        stmt = (
            sa.select(KnowledgeChunkModel)
            .order_by(KnowledgeChunkModel.embedding.op("<=>")(query_embedding))
            .limit(k)
        )
        rows = session.execute(stmt).scalars().all()
        logger.debug(
            "top_k query executed",
            extra={"k": k, "results_returned": len(rows)},
        )
        return [_to_knowledge_chunk(row) for row in rows]

    def get_chunk_count(self, session: Session) -> int:
        """Return total count of KnowledgeChunk rows in the table."""
        result = session.execute(sa.select(sa.func.count()).select_from(KnowledgeChunkModel))
        return int(result.scalar_one())

    def chunk_exists(self, session: Session, content_hash: str) -> bool:
        """Return True if a chunk with the given content_hash already exists."""
        stmt = sa.select(KnowledgeChunkModel).where(
            KnowledgeChunkModel.content_hash == content_hash
        )
        row = session.scalars(stmt).first()
        return row is not None


# ---------------------------------------------------------------------------
# ORM → domain mapper
# ---------------------------------------------------------------------------


def _to_knowledge_chunk(row: KnowledgeChunkModel) -> KnowledgeChunk:
    """Map a KnowledgeChunkModel ORM row to the KnowledgeChunk domain object."""
    return KnowledgeChunk(
        id=row.id,
        source_file=row.source_file,
        category=KnowledgeCategory(row.category),
        chunk_index=row.chunk_index,
        content=row.content,
        content_hash=row.content_hash,
        embedding=list(row.embedding),
        created_at=row.created_at if isinstance(row.created_at, datetime) else datetime.now(),
    )
