"""Local text extraction from resume files (PDF / DOCX).

Pure, offline extraction: no external AI-SDK or LLM provider imports are
permitted (AC-IMPORT-C05). Takes file bytes, validates the declared type against
the filename extension, enforces a size cap, and returns non-empty extracted text
— or raises a typed error. No LLM call, no network, no fastapi import.
"""

from __future__ import annotations

import io
import zipfile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.types.enums import MIME_DOCX, MIME_PDF

# Max upload size: 5 MB (data-models.md §0).
MAX_FILE_BYTES = 5_242_880


class ExtractionError(Exception):
    """Raised when the file cannot be extracted (corrupt/empty/protected).

    The message is generic and never contains file content or PII.
    """


class InvalidFileTypeError(Exception):
    """Raised when the MIME type / extension is disallowed or the file is too large.

    The message is generic and never contains file content or PII.
    """


def extract_text(file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Extract raw text from a PDF or DOCX file.

    Validates that the MIME type AND filename extension both name the same
    allowed format, enforces the 5 MB cap, then extracts text locally.

    Args:
        file_bytes: Raw uploaded file content.
        mime_type: Declared MIME type; must match the allowed set.
        filename: Original filename; its extension must match ``mime_type``.

    Returns:
        Non-empty extracted text.

    Raises:
        InvalidFileTypeError: Disallowed MIME/extension, mismatch, or oversize file.
        ExtractionError: Corrupt, empty, password-protected, or image-only file.
    """
    if len(file_bytes) > MAX_FILE_BYTES:
        raise InvalidFileTypeError("File exceeds the maximum allowed size")

    name_lower = filename.lower()
    if mime_type == MIME_PDF and name_lower.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    if mime_type == MIME_DOCX and name_lower.endswith(".docx"):
        return _extract_docx(file_bytes)

    raise InvalidFileTypeError("Unsupported or mismatched file type")


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes, rejecting encrypted/corrupt/empty files."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise ExtractionError("Password-protected files are not supported")
        parts = [page.extract_text() or "" for page in reader.pages]
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, OSError, KeyError) as exc:
        raise ExtractionError("Could not read the PDF file") from exc

    return _require_non_empty("".join(parts))


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes, rejecting corrupt/empty files."""
    try:
        document = Document(io.BytesIO(file_bytes))
        parts = [para.text for para in document.paragraphs]
    except (PackageNotFoundError, zipfile.BadZipFile, ValueError, OSError, KeyError) as exc:
        raise ExtractionError("Could not read the DOCX file") from exc

    return _require_non_empty("\n".join(parts))


def _require_non_empty(text: str) -> str:
    """Return ``text`` if it has non-whitespace content, else raise ExtractionError."""
    if not text.strip():
        raise ExtractionError("No extractable text found in the file")
    return text
