"""Prompt templates for AI features.

Prompts live in the service layer. The system instruction is authored here as
the highest-priority contract; untrusted user text is always delimited by the
prompt builders in this package, never concatenated into the system message.
"""

from app.services.ai.prompts.resume_structuring import (
    RESUME_STRUCTURING_SYSTEM,
    build_resume_structuring_prompt,
)

__all__ = [
    "RESUME_STRUCTURING_SYSTEM",
    "build_resume_structuring_prompt",
]
