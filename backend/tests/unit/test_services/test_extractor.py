"""Unit tests for app/services/parsing/extractor.py.

All extraction is local: no LLM, no network. These tests build valid PDF/DOCX
bytes in memory, then exercise the type/size validation and error paths. A
dedicated test asserts the module imports NOTHING from the LLM/groq layers
(AC-IMPORT-C05).
"""

from __future__ import annotations

import io
import pathlib

import pytest
from docx import Document
from pypdf import PdfWriter

from app.services.parsing.extractor import (
    MAX_FILE_BYTES,
    ExtractionError,
    InvalidFileTypeError,
    extract_text,
)
from app.types.enums import MIME_DOCX, MIME_PDF

# ---------------------------------------------------------------------------
# In-memory file builders
# ---------------------------------------------------------------------------


def make_test_pdf(text: str = "Test resume content Python FastAPI") -> bytes:
    """Build a minimal one-page PDF that contains extractable text.

    ``PdfWriter`` cannot draw text directly, so we render a tiny text-bearing
    PDF by hand and round-trip it through ``PdfWriter`` to guarantee validity.
    """
    raw = _handmade_text_pdf(text)
    writer = PdfWriter(clone_from=io.BytesIO(raw))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _handmade_text_pdf(text: str) -> bytes:
    """Construct a valid single-page PDF whose content stream draws ``text``."""
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objects) + 1,
        xref_pos,
    )
    return bytes(out)


def make_test_docx(text: str = "Test resume content Python FastAPI") -> bytes:
    """Build a minimal valid DOCX carrying one paragraph of ``text``."""
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_valid_pdf_returns_text() -> None:
    result = extract_text(make_test_pdf(), MIME_PDF, "resume.pdf")
    assert isinstance(result, str)
    assert result.strip()


def test_valid_docx_returns_text() -> None:
    result = extract_text(make_test_docx(), MIME_DOCX, "resume.docx")
    assert "Test resume content" in result


def test_extension_check_is_case_insensitive() -> None:
    result = extract_text(make_test_pdf(), MIME_PDF, "RESUME.PDF")
    assert result.strip()


# ---------------------------------------------------------------------------
# Type / size validation
# ---------------------------------------------------------------------------


def test_wrong_mime_type_rejected() -> None:
    with pytest.raises(InvalidFileTypeError):
        extract_text(make_test_pdf(), "text/plain", "resume.pdf")


def test_pdf_mime_with_txt_extension_rejected() -> None:
    with pytest.raises(InvalidFileTypeError):
        extract_text(make_test_pdf(), MIME_PDF, "resume.txt")


def test_docx_mime_with_pdf_extension_rejected() -> None:
    with pytest.raises(InvalidFileTypeError):
        extract_text(make_test_docx(), MIME_DOCX, "resume.pdf")


def test_oversize_file_rejected() -> None:
    big = b"%PDF-1.4\n" + b"0" * (MAX_FILE_BYTES + 1)
    with pytest.raises(InvalidFileTypeError):
        extract_text(big, MIME_PDF, "resume.pdf")


# ---------------------------------------------------------------------------
# Extraction failure paths
# ---------------------------------------------------------------------------


def test_corrupt_pdf_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"not a real pdf at all", MIME_PDF, "resume.pdf")


def test_empty_pdf_bytes_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"", MIME_PDF, "resume.pdf")


def test_corrupt_docx_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"not a real docx", MIME_DOCX, "resume.docx")


def test_blank_docx_raises_extraction_error() -> None:
    # A DOCX whose only paragraph is whitespace has no extractable text.
    with pytest.raises(ExtractionError):
        extract_text(make_test_docx("   "), MIME_DOCX, "resume.docx")


# ---------------------------------------------------------------------------
# Purity: no LLM / groq imports (AC-IMPORT-C05)
# ---------------------------------------------------------------------------


def test_password_protected_pdf_raises_extraction_error() -> None:
    """An AES-128/RC4 encrypted PDF must raise ExtractionError (not crash)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("password123")
    buf = io.BytesIO()
    writer.write(buf)
    encrypted_bytes = buf.getvalue()

    with pytest.raises(ExtractionError, match="Password-protected"):
        extract_text(encrypted_bytes, MIME_PDF, "resume.pdf")


def test_extractor_has_no_llm_imports() -> None:
    import ast

    source = pathlib.Path("src/app/services/parsing/extractor.py").read_text(encoding="utf-8")
    forbidden = ("llm_client", "llm_provider", "groq_provider", "groq")

    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    for mod in imported:
        parts = mod.split(".")
        for bad in forbidden:
            assert bad not in parts, f"extractor must not import {bad} (found {mod})"
