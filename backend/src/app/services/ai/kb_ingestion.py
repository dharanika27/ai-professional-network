"""Knowledge base ingestion service (E5-S2).

Implements:
  - chunk_markdown — split markdown into bounded chunks at heading/paragraph boundaries
  - ingest_kb      — read kb_dir/*.md, chunk, embed, and idempotently insert rows

Chunking strategy (rag-pipeline.md §3.1):
  - Split at ## headings and blank-line paragraph boundaries
  - Target chunk size: ~500-800 tokens (~2000-3200 chars at 4 chars/token)
  - Hard ceiling: ~1000 tokens (~4000 chars)
  - Never split mid-sentence — always break at natural boundaries
  - chunk_index is 0-based per source file
  - content_hash = sha256(content)
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import re
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import KnowledgeChunkModel
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.ai.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Filename → category mapping (rag-pipeline.md §3.1)
# ---------------------------------------------------------------------------

FILENAME_TO_CATEGORY: dict[str, str] = {
    "ats_best_practices.md": "ats",
    "resume_writing.md": "resume",
    "profile_optimization.md": "profile",
    "interview_prep.md": "interview",
    "career_guidance.md": "career",
}


# ---------------------------------------------------------------------------
# Data transfer object for chunk data before DB insertion
# ---------------------------------------------------------------------------


@dataclass
class ChunkData:
    """Intermediate chunk data produced by chunk_markdown."""

    source_file: str
    category: str
    chunk_index: int
    content: str
    content_hash: str


# ---------------------------------------------------------------------------
# Chunking logic
# ---------------------------------------------------------------------------


def _sha256_hex(text: str) -> str:
    """Return the SHA-256 hex digest of the given text."""
    return hashlib.sha256(text.encode()).hexdigest()


def _split_into_sections(content: str) -> list[str]:
    """Split markdown content on ## headings, keeping each section together.

    Returns a list of text blocks. The ## heading line is included at the
    start of its section block.
    """
    # Split on lines that start with ## (but not ### or deeper)
    heading_pattern = re.compile(r"^##\s", re.MULTILINE)
    parts = heading_pattern.split(content)

    sections: list[str] = []
    for i, part in enumerate(parts):
        stripped = part.strip()
        if not stripped:
            continue
        # Re-attach the ## prefix (split consumed it) for parts after the first
        if i > 0:
            sections.append("## " + part.strip())
        else:
            sections.append(part.strip())
    return sections


def _split_section_on_paragraphs(section: str) -> list[str]:
    """Split a section into paragraphs separated by blank lines."""
    paragraphs = re.split(r"\n\s*\n", section)
    return [p.strip() for p in paragraphs if p.strip()]


def _merge_paragraphs_into_chunks(
    paragraphs: list[str],
    max_chars: int,
) -> list[str]:
    """Greedily merge paragraphs into chunks not exceeding max_chars.

    Never merges a paragraph that would cause the chunk to exceed max_chars.
    If a single paragraph exceeds max_chars on its own, it is placed in its
    own chunk (sentence boundary enforcement would add too much complexity
    for MVP — the paragraph itself is the natural boundary).
    """
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        # +1 accounts for the blank line separator when joining
        separator_len = 2 if current_parts else 0

        if current_parts and current_len + separator_len + para_len > max_chars:
            # Flush current accumulation
            chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_len = para_len
        else:
            current_parts.append(para)
            current_len += separator_len + para_len

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def chunk_markdown(
    content: str,
    source_file: str,
    max_chars: int = 4000,
) -> list[ChunkData]:
    """Split markdown content into bounded chunks at heading/paragraph boundaries.

    Returns list of ChunkData with source_file, category, chunk_index,
    content, and content_hash.

    Chunks break at ## headings and blank lines. Never splits mid-sentence.
    chunk_index is 0-based across all chunks for this source_file.
    """
    if not content.strip():
        return []

    category = FILENAME_TO_CATEGORY.get(source_file, "")
    sections = _split_into_sections(content)

    raw_chunks: list[str] = []
    for section in sections:
        paragraphs = _split_section_on_paragraphs(section)
        merged = _merge_paragraphs_into_chunks(paragraphs, max_chars=max_chars)
        raw_chunks.extend(merged)

    result: list[ChunkData] = []
    for idx, chunk_content in enumerate(raw_chunks):
        if not chunk_content.strip():  # pragma: no cover
            continue
        result.append(
            ChunkData(
                source_file=source_file,
                category=category,
                chunk_index=idx,
                content=chunk_content,
                content_hash=_sha256_hex(chunk_content),
            )
        )

    logger.debug(
        "chunk_markdown complete",
        extra={
            "source_file": source_file,
            "chunks_produced": len(result),
            "max_chars": max_chars,
        },
    )
    return result


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------


def _build_model(chunk: ChunkData, embedding: list[float]) -> KnowledgeChunkModel:
    """Construct a KnowledgeChunkModel from a ChunkData and its embedding."""
    return KnowledgeChunkModel(
        id=uuid.uuid4(),
        source_file=chunk.source_file,
        category=chunk.category,
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        content_hash=chunk.content_hash,
        embedding=embedding,
    )


def _process_file(
    session: Session,
    provider: EmbeddingProvider,
    knowledge_repo: KnowledgeRepository,
    source_file: str,
    content: str,
) -> int:
    """Chunk one file, embed new chunks, and upsert them. Returns count inserted."""
    chunks = chunk_markdown(content, source_file=source_file)
    if not chunks:
        logger.warning(
            "No chunks produced for file",
            extra={"source_file": source_file},
        )
        return 0

    new_chunks = [
        c
        for c in chunks
        if not knowledge_repo.chunk_exists(
            session=session,
            content_hash=c.content_hash,
        )
    ]

    if not new_chunks:
        logger.info(
            "All chunks already exist, skipping embedding",
            extra={"source_file": source_file, "total_chunks": len(chunks)},
        )
        return 0

    texts = [c.content for c in new_chunks]
    embeddings = provider.embed_batch(texts)

    inserted = 0
    for chunk, embedding in zip(new_chunks, embeddings, strict=True):
        model = _build_model(chunk, embedding)
        knowledge_repo.upsert_chunk(session=session, chunk=model)
        inserted += 1

    logger.info(
        "File ingested",
        extra={
            "source_file": source_file,
            "chunks_inserted": inserted,
            "chunks_skipped": len(chunks) - inserted,
        },
    )
    return inserted


def ingest_kb(
    session: Session,
    provider: EmbeddingProvider,
    kb_dir: pathlib.Path,
    knowledge_repo: KnowledgeRepository,
) -> dict[str, int]:
    """Read kb_dir/*.md, chunk, embed, and idempotently insert KnowledgeChunk rows.

    Returns dict of {filename: chunks_inserted} (0 for already-existing chunks).
    Transaction boundary: caller owns commit/rollback.
    Idempotency: pre-checks content_hash existence before embedding to avoid
    re-embedding chunks that are already stored.
    """
    results: dict[str, int] = {}

    for filename in sorted(FILENAME_TO_CATEGORY.keys()):
        filepath = kb_dir / filename
        if not filepath.exists():
            logger.warning(
                "KB file not found, skipping",
                extra={"filepath": str(filepath)},
            )
            continue

        content = filepath.read_text(encoding="utf-8")
        inserted = _process_file(
            session=session,
            provider=provider,
            knowledge_repo=knowledge_repo,
            source_file=filename,
            content=content,
        )
        results[filename] = inserted

    logger.info(
        "ingest_kb complete",
        extra={
            "files_processed": len(results),
            "total_inserted": sum(results.values()),
        },
    )
    return results
