"""Unit tests for kb_ingestion service (E5-S2).

Tests written FIRST (TDD). Each test defines a behavior contract.
Uses FakeEmbeddingProvider to avoid loading sentence-transformers model.
"""

from __future__ import annotations

import hashlib
import pathlib
from unittest.mock import MagicMock

import pytest

from app.services.ai.kb_ingestion import chunk_markdown, ingest_kb

# ---------------------------------------------------------------------------
# Fake embedding provider — deterministic, no model loading
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic embedding provider for unit tests."""

    def embed_text(self, text: str) -> list[float]:
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % 1000
        return [float(seed + i) / 10000 for i in range(384)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_MARKDOWN = """\
# Main Title

Introduction paragraph with some content about the topic.

## Section One

Content for section one. This is a paragraph that discusses the first topic
in some detail with multiple sentences to give it substance.

More content within section one. Another paragraph here.

## Section Two

Content for section two. This section covers a different area of the topic
with its own distinct content and information.

Final paragraph of section two with closing thoughts.
"""


@pytest.fixture()
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


# ---------------------------------------------------------------------------
# chunk_markdown tests
# ---------------------------------------------------------------------------


def test_chunk_markdown_splits_on_headings() -> None:
    """Chunks must break at ## headings, keeping each section together."""
    chunks = chunk_markdown(SAMPLE_MARKDOWN, source_file="ats_best_practices.md")

    assert len(chunks) >= 2, "Expected multiple chunks from headings"
    # Verify section two content is in a separate chunk from section one
    section_one_chunk = next((c for c in chunks if "Content for section one" in c.content), None)
    section_two_chunk = next((c for c in chunks if "Content for section two" in c.content), None)
    assert section_one_chunk is not None, "Section one content must appear in a chunk"
    assert section_two_chunk is not None, "Section two content must appear in a chunk"
    # They must be in different chunks
    assert section_one_chunk is not section_two_chunk


def test_chunk_markdown_respects_max_chars() -> None:
    """Merging stops at max_chars: two paragraphs that together exceed the limit
    must NOT be merged into a single chunk.

    Note: a single paragraph that itself exceeds max_chars is placed in its own
    chunk (the chunker does not split mid-word/mid-sentence within a paragraph).
    """
    # Two medium paragraphs that together exceed max_chars=200 but are each fine alone
    para_a = "A " * 120  # 240 chars, below 200 only individually
    para_b = "B " * 80  # 160 chars

    # Each paragraph alone fits within 250 chars, but combined they exceed 200
    content = f"## Section One\n\n{para_a}\n\n{para_b}\n"
    chunks = chunk_markdown(content, source_file="resume_writing.md", max_chars=200)

    # The two paragraphs must NOT be merged since together they exceed 200
    combined_content = " ".join(c.content for c in chunks)
    assert para_a.strip() in combined_content, "para_a must appear in some chunk"
    assert para_b.strip() in combined_content, "para_b must appear in some chunk"

    # Each chunk that results from normal merging (not single-para overflow)
    # should be <= max_chars; any chunk > max_chars is a single paragraph chunk
    for chunk in chunks:
        chunk_paragraphs = chunk.content.split("\n\n")
        if len(chunk_paragraphs) > 1:
            # Multi-paragraph chunk must respect max_chars (no over-merging)
            assert len(chunk.content) <= 200, (
                f"Multi-paragraph chunk exceeds max_chars=200: len={len(chunk.content)}"
            )


def test_chunk_markdown_assigns_correct_indices() -> None:
    """chunk_index must be 0-based sequential integers."""
    chunks = chunk_markdown(SAMPLE_MARKDOWN, source_file="interview_prep.md")

    assert len(chunks) >= 1
    indices = [c.chunk_index for c in chunks]
    expected = list(range(len(chunks)))
    assert indices == expected, f"Expected {expected}, got {indices}"


def test_chunk_markdown_content_hash_sha256() -> None:
    """content_hash must equal sha256(content) in hex."""
    chunks = chunk_markdown(SAMPLE_MARKDOWN, source_file="career_guidance.md")

    for chunk in chunks:
        expected_hash = hashlib.sha256(chunk.content.encode()).hexdigest()
        assert chunk.content_hash == expected_hash, (
            f"content_hash mismatch for chunk_index={chunk.chunk_index}: "
            f"expected={expected_hash[:16]}..., got={chunk.content_hash[:16]}..."
        )


def test_chunk_markdown_source_file_set() -> None:
    """source_file on each ChunkData must match the input source_file argument."""
    source = "profile_optimization.md"
    chunks = chunk_markdown(SAMPLE_MARKDOWN, source_file=source)

    for chunk in chunks:
        assert chunk.source_file == source


def test_chunk_markdown_category_derived_from_filename() -> None:
    """category on ChunkData must map correctly from filename."""
    category_cases: list[tuple[str, str]] = [
        ("ats_best_practices.md", "ats"),
        ("resume_writing.md", "resume"),
        ("profile_optimization.md", "profile"),
        ("interview_prep.md", "interview"),
        ("career_guidance.md", "career"),
    ]
    for filename, expected_category in category_cases:
        chunks = chunk_markdown("## Section\n\nSome content here.\n", source_file=filename)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.category == expected_category, (
                f"filename={filename} expected category={expected_category}, got={chunk.category}"
            )


def test_chunk_markdown_empty_content_returns_empty_list() -> None:
    """Empty markdown content must return an empty list, not raise."""
    chunks = chunk_markdown("", source_file="ats_best_practices.md")
    assert chunks == []


def test_chunk_markdown_no_empty_chunks() -> None:
    """No chunk should have empty or whitespace-only content."""
    chunks = chunk_markdown(SAMPLE_MARKDOWN, source_file="resume_writing.md")

    for chunk in chunks:
        assert chunk.content.strip(), f"Chunk {chunk.chunk_index} has empty content"


# ---------------------------------------------------------------------------
# ingest_kb tests
# ---------------------------------------------------------------------------


def test_ingest_kb_skips_existing_chunks(
    tmp_path: pathlib.Path, fake_provider: FakeEmbeddingProvider
) -> None:
    """When chunk_exists returns True, embed_batch must NOT be called."""
    # Create a minimal KB file
    kb_file = tmp_path / "ats_best_practices.md"
    kb_file.write_text("## ATS Section\n\nContent about ATS parsing for testing.\n")

    mock_repo = MagicMock()
    mock_repo.chunk_exists.return_value = True  # all chunks already exist

    mock_session = MagicMock()
    provider_spy = MagicMock(wraps=fake_provider)

    result = ingest_kb(
        session=mock_session,
        provider=provider_spy,
        kb_dir=tmp_path,
        knowledge_repo=mock_repo,
    )

    provider_spy.embed_batch.assert_not_called()
    provider_spy.embed_text.assert_not_called()
    # Result should show 0 chunks inserted for the file
    assert result.get("ats_best_practices.md", 0) == 0


def test_ingest_kb_embeds_new_chunks(
    tmp_path: pathlib.Path, fake_provider: FakeEmbeddingProvider
) -> None:
    """When chunk_exists returns False, embed_batch must be called with chunk content."""
    kb_file = tmp_path / "resume_writing.md"
    kb_file.write_text(
        "## Strong Verbs\n\nUse action verbs like achieved and delivered.\n"
        "\n## Metrics\n\nQuantify achievements with percentages and dollars.\n"
    )

    mock_repo = MagicMock()
    mock_repo.chunk_exists.return_value = False  # no chunks exist yet

    mock_session = MagicMock()

    result = ingest_kb(
        session=mock_session,
        provider=fake_provider,
        kb_dir=tmp_path,
        knowledge_repo=mock_repo,
    )

    assert result.get("resume_writing.md", 0) > 0
    mock_repo.upsert_chunk.assert_called()


def test_ingest_kb_returns_per_file_counts(
    tmp_path: pathlib.Path, fake_provider: FakeEmbeddingProvider
) -> None:
    """ingest_kb must return a dict mapping filename → chunks inserted."""
    (tmp_path / "ats_best_practices.md").write_text("## Section A\n\nATS parsing content here.\n")
    (tmp_path / "resume_writing.md").write_text("## Section B\n\nResume writing content here.\n")

    mock_repo = MagicMock()
    mock_repo.chunk_exists.return_value = False
    mock_session = MagicMock()

    result = ingest_kb(
        session=mock_session,
        provider=fake_provider,
        kb_dir=tmp_path,
        knowledge_repo=mock_repo,
    )

    assert "ats_best_practices.md" in result
    assert "resume_writing.md" in result
    assert isinstance(result["ats_best_practices.md"], int)
    assert isinstance(result["resume_writing.md"], int)


def test_ingest_kb_ignores_unknown_filenames(
    tmp_path: pathlib.Path, fake_provider: FakeEmbeddingProvider
) -> None:
    """Files not in FILENAME_TO_CATEGORY must be skipped without error."""
    (tmp_path / "unknown_file.md").write_text("## Section\n\nSome content.\n")
    (tmp_path / "ats_best_practices.md").write_text("## ATS\n\nATS best practices content.\n")

    mock_repo = MagicMock()
    mock_repo.chunk_exists.return_value = False
    mock_session = MagicMock()

    result = ingest_kb(
        session=mock_session,
        provider=fake_provider,
        kb_dir=tmp_path,
        knowledge_repo=mock_repo,
    )

    assert "unknown_file.md" not in result
    assert "ats_best_practices.md" in result


def test_chunk_markdown_skips_empty_chunks() -> None:
    """chunk_markdown must skip chunks whose stripped content is empty.

    Covers kb_ingestion.py line 164 (the `continue` inside the empty-content guard).
    """
    # Content where some sections are whitespace-only after splitting
    content = "## Section A\n\nReal content here.\n\n## Section B\n\n   \n\n## Section C\n\nMore content.\n"
    chunks = chunk_markdown(content, source_file="ats_best_practices.md")

    # No chunk should have empty or whitespace-only content
    for chunk in chunks:
        assert chunk.content.strip(), f"Empty chunk at index {chunk.chunk_index}: {chunk.content!r}"

    # We should still get chunks from the non-empty sections
    assert len(chunks) >= 1


def test_ingest_kb_returns_zero_for_empty_file(
    tmp_path: pathlib.Path, fake_provider: FakeEmbeddingProvider
) -> None:
    """_process_file returns 0 and logs a warning when chunk_markdown produces no chunks.

    Covers kb_ingestion.py lines 214-218 (the `if not chunks:` warning path).
    """
    # Whitespace-only file produces no chunks
    kb_file = tmp_path / "ats_best_practices.md"
    kb_file.write_text("   \n\n   \n")

    mock_repo = MagicMock()
    mock_repo.chunk_exists.return_value = False
    mock_session = MagicMock()

    result = ingest_kb(
        session=mock_session,
        provider=fake_provider,
        kb_dir=tmp_path,
        knowledge_repo=mock_repo,
    )

    # Should report 0 inserted for the whitespace-only file
    assert result.get("ats_best_practices.md", -1) == 0
    # embed_batch must NOT be called for a file that produces no chunks
    mock_repo.upsert_chunk.assert_not_called()
