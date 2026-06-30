"""Structured sub-document schemas for JSONB columns.

These typed shapes are validated by Pydantic and stored inside JSONB columns.
They are also reused as API DTO fragments. Matches data-models.md §3 exactly.

No imports from app/config, app/db, app/repositories, app/services, or app/api.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContactInfo(BaseModel):
    """PII contact block within a StructuredResume. data-models.md §3.5.1."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    """Single education entry. data-models.md §3.1."""

    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str | None = None
    field: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    grade: str | None = None


class ExperienceItem(BaseModel):
    """Single work experience entry. data-models.md §3.2."""

    model_config = ConfigDict(extra="forbid")

    company: str
    title: str
    start_date: str | None = None  # YYYY-MM
    end_date: str | None = None  # YYYY-MM or null if current
    current: bool = False
    description: str | None = None


class CertificationItem(BaseModel):
    """Single certification entry. data-models.md §3.3."""

    model_config = ConfigDict(extra="forbid")

    name: str
    issuer: str | None = None
    issued_date: str | None = None  # YYYY-MM


class ProjectItem(BaseModel):
    """Single project entry. data-models.md §3.4."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    url: str | None = None
    technologies: list[str] = Field(default_factory=list)


class StructuredResume(BaseModel):
    """Parsed resume with exactly the BRD six-key schema. data-models.md §3.5.

    Keys: {contact, skills, education, experience, certifications, projects}.
    Stored in resumes.structured_content JSONB. PII (contains contact).
    """

    model_config = ConfigDict(extra="forbid")

    contact: ContactInfo
    skills: list[str] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)


class ReviewItem(BaseModel):
    """A single AI suggestion or observation. data-models.md §3.8."""

    model_config = ConfigDict(extra="forbid")

    text: str
    source_id: str | None = None


class Citation(BaseModel):
    """RAG grounding citation. data-models.md §3.9."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_file: str
    snippet: str | None = None
