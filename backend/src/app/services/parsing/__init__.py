"""Local resume parsing sub-package.

``extractor`` pulls raw text from PDF/DOCX bytes with NO LLM involvement.
``structurer`` sends that raw text through the LLMClient to obtain a validated
``StructuredResume``.
"""

from app.services.parsing.extractor import (
    ExtractionError,
    InvalidFileTypeError,
    extract_text,
)
from app.services.parsing.structurer import structure_resume

__all__ = [
    "ExtractionError",
    "InvalidFileTypeError",
    "extract_text",
    "structure_resume",
]
