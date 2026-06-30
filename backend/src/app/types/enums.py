"""Enumeration types for the AI Professional Network domain.

All enum value sets match data-models.md §0.
Stored as TEXT with CHECK constraints in PostgreSQL (portable, avoids native enum migration pain).
"""

from enum import StrEnum


class ThemePreference(StrEnum):
    """User interface theme setting."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class ParseStatus(StrEnum):
    """Resume parse lifecycle state."""

    PENDING = "pending"
    PARSED = "parsed"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    """AI review / optimization job lifecycle state."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class JobMatchRunStatus(StrEnum):
    """Job match run lifecycle state."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AIFeature(StrEnum):
    """Which AI feature triggered a request log entry."""

    RESUME_STRUCTURING = "resume_structuring"
    RESUME_REVIEW = "resume_review"
    PROFILE_OPTIMIZATION = "profile_optimization"
    JOB_MATCHING = "job_matching"


class AIOutcome(StrEnum):
    """Outcome of an AI request."""

    SUCCESS = "success"
    RETRY_SUCCESS = "retry_success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INVALID_SCHEMA = "invalid_schema"
    RATE_LIMITED = "rate_limited"


class KnowledgeCategory(StrEnum):
    """RAG knowledge-base chunk category."""

    ATS = "ats"
    RESUME = "resume"
    PROFILE = "profile"
    INTERVIEW = "interview"
    CAREER = "career"


class JobSource(StrEnum):
    """How a job posting entered the system."""

    SEED = "seed"
    API = "api"


# MIME type constants — two allowed types per data-models.md §0
MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({MIME_PDF, MIME_DOCX})


class MimeType(StrEnum):
    """Allowed resume MIME types."""

    PDF = MIME_PDF
    DOCX = MIME_DOCX
