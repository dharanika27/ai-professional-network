"""Centralized LLM configuration.

Single place for model IDs, per-feature token budgets, the 60 s timeout,
retry count, and provider selection. Changing provider or model requires
only an env-var change — no code change.

Amendment 001: provider is Groq (not Anthropic).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings


@dataclass(frozen=True)
class LLMConfig:
    """Immutable LLM configuration derived from Settings."""

    provider: str
    review_model: str
    default_model: str
    max_tokens: int
    timeout_seconds: int
    max_retries: int
    ai_rate_limit_per_hour: int
    groq_api_key: str | None


def build_llm_config(settings: Settings) -> LLMConfig:
    """Construct LLMConfig from the application Settings."""
    return LLMConfig(
        provider=settings.llm_provider,
        review_model=settings.llm_review_model,
        default_model=settings.llm_default_model,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        ai_rate_limit_per_hour=settings.ai_rate_limit_per_hour,
        groq_api_key=settings.groq_api_key,
    )
