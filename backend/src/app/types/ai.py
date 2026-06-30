"""AI content schemas — outputs that Claude/LLM must validate against.

ResumeReviewContent and ProfileOptimizationContent are the JSON shapes
that AI feature outputs must conform to before being placed in a response DTO.

No imports from app/config, app/db, app/repositories, app/services, or app/api.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.types.structured import Citation, ReviewItem


class ResumeReviewContent(BaseModel):
    """AI resume critique output schema. data-models.md §3.6."""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str
    strengths: list[ReviewItem] = Field(default_factory=list)
    weaknesses: list[ReviewItem] = Field(default_factory=list)
    ats_issues: list[ReviewItem] = Field(default_factory=list)
    suggestions: list[ReviewItem] = Field(default_factory=list)


class ProfileOptimizationContent(BaseModel):
    """AI profile improvement output schema. data-models.md §3.7."""

    model_config = ConfigDict(extra="forbid")

    headline_suggestions: list[ReviewItem] = Field(default_factory=list)
    summary_suggestion: ReviewItem | None = None
    missing_skills: list[str] = Field(default_factory=list)
    section_suggestions: list[ReviewItem] = Field(default_factory=list)


__all__ = [
    "Citation",
    "ProfileOptimizationContent",
    "ResumeReviewContent",
    "ReviewItem",
]
