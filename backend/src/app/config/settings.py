"""Centralized environment-driven Settings.

Loads all configuration from environment variables via pydantic-settings.
Fails fast at startup when required secrets DATABASE_URL or JWT_SECRET are absent.

Amendment 001: No third-party LLM API key is required for Groups A-B.
GROQ_API_KEY is optional here; required from Epic E6.
Only DATABASE_URL and JWT_SECRET are required fail-fast fields.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single typed settings object for the entire application.

    Required at startup: DATABASE_URL, JWT_SECRET.
    All other fields have defaults or are optional.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database (required)
    # ------------------------------------------------------------------
    database_url: str = Field(
        ...,
        description="PostgreSQL DSN. Required. Fail-fast if absent.",
    )

    # ------------------------------------------------------------------
    # JWT (required)
    # ------------------------------------------------------------------
    jwt_secret: str = Field(
        ...,
        description="HS256 signing secret. Required. Fail-fast if absent.",
    )
    jwt_access_ttl_seconds: int = Field(
        default=900,
        description="Access token lifetime in seconds (default 15 min).",
    )
    jwt_refresh_ttl_seconds: int = Field(
        default=2_592_000,
        description="Refresh token lifetime in seconds (default 30 days).",
    )

    # ------------------------------------------------------------------
    # LLM provider (all optional in Group A — no LLM calls here)
    # ------------------------------------------------------------------
    llm_provider: str = Field(
        default="groq",
        description="LLM provider identifier. Default: groq.",
    )
    groq_api_key: str | None = Field(
        default=None,
        description="Groq API key. Optional in Group A; required from Epic E6.",
    )
    llm_timeout_seconds: int = Field(
        default=60,
        description="LLM request timeout in seconds.",
    )
    ai_rate_limit_per_hour: int = Field(
        default=10,
        description="Per-user AI request rate limit per hour.",
    )
    llm_review_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model for resume review.",
    )
    llm_default_model: str = Field(
        default="llama-3.1-8b-instant",
        description="Groq model for structuring / optimization / matching.",
    )
    llm_max_tokens: int = Field(
        default=4096,
        description="Maximum output tokens per LLM call.",
    )
    llm_max_retries: int = Field(
        default=1,
        description="Maximum LLM retry count on schema validation failure.",
    )

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------
    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="Sentence-transformers model name for embeddings.",
    )
    embedding_dim: int = Field(
        default=384,
        description="Embedding vector dimension. Must match model output.",
    )

    # ------------------------------------------------------------------
    # Upload policy
    # ------------------------------------------------------------------
    max_upload_mb: int = Field(
        default=5,
        description="Maximum resume upload size in megabytes.",
    )

    # ------------------------------------------------------------------
    # Frontend / CORS
    # ------------------------------------------------------------------
    frontend_origin: str = Field(
        default="http://localhost:3000",
        description="Allowed CORS origin for the frontend.",
    )

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    storage_dir: str = Field(
        default="data/resumes",
        description="Local non-web-served directory for resume file storage.",
    )

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------
    env: str = Field(default="development", description="Runtime environment.")
    log_level: str = Field(default="INFO", description="Log verbosity.")

    # ------------------------------------------------------------------
    # RAG retrieval (Group C, E5-S3)
    # ------------------------------------------------------------------
    rag_top_k: int = Field(
        default=5,
        description="Default number of knowledge chunks to retrieve (RAG_TOP_K).",
    )
    rag_min_similarity: float = Field(
        default=0.0,
        description="Minimum cosine similarity score for RAG retrieval (RAG_MIN_SIMILARITY).",
    )

    # ------------------------------------------------------------------
    # Argon2 hashing params
    # ------------------------------------------------------------------
    argon2_time_cost: int = Field(default=3)
    argon2_memory_kib: int = Field(default=65536)
    argon2_parallelism: int = Field(default=4)

    @field_validator("max_upload_mb")
    @classmethod
    def validate_upload_mb(cls, v: int) -> int:
        """Upload limit must be a positive integer."""
        if v <= 0:
            raise ValueError("max_upload_mb must be a positive integer")
        return v

    @field_validator("embedding_dim")
    @classmethod
    def validate_embedding_dim(cls, v: int) -> int:
        """Embedding dimension must be positive."""
        if v <= 0:
            raise ValueError("embedding_dim must be a positive integer")
        return v

    @property
    def max_upload_bytes(self) -> int:
        """Convenience: upload limit in bytes."""
        return self.max_upload_mb * 1024 * 1024


def get_settings() -> Settings:
    """Load and return a Settings instance.

    Call once at startup; the result should be cached / injected.
    Raises pydantic_settings.ValidationError if required vars are missing.
    """
    return Settings()
