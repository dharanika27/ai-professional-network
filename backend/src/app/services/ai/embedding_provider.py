"""EmbeddingProvider interface and local bge-small-en-v1.5 implementation.

The Protocol is the only thing callers should import.
The concrete BGEEmbeddingProvider is wired at startup; callers never see it.
No sentence-transformers import outside this file (AC-IMPORT-03).

Model loads lazily on first embed call (AC-BEHAV-05 singleton).
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Type alias for a single embedding vector
Vector = list[float]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface for text embedding providers.

    Callers depend ONLY on this protocol — never on the concrete class.
    Swapping providers requires changing only the wiring (DI / config),
    not any calling service.
    """

    def embed_text(self, text: str) -> Vector:
        """Embed a single piece of text and return a 384-dim float vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        """Embed a list of texts and return a list of 384-dim float vectors.

        embed_batch([]) returns [] without error.
        """
        ...


class BGEEmbeddingProvider:
    """Local BAAI/bge-small-en-v1.5 implementation of EmbeddingProvider.

    Loads the model lazily on first call (singleton per process).
    Returns 384-dimension float vectors. Deterministic: same input → same output.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self._model_name = model_name
        self._model: object | None = None
        self._lock = threading.Lock()

    def _load_model(self) -> object:
        """Load the sentence-transformers model (thread-safe, once per process)."""
        with self._lock:
            if self._model is None:
                # Import deferred so callers that never embed don't pay startup cost
                from sentence_transformers import (
                    SentenceTransformer,  # type: ignore[import-untyped,unused-ignore]
                )

                logger.info(
                    "Loading embedding model",
                    extra={"model": self._model_name},
                )
                self._model = SentenceTransformer(self._model_name)
                logger.info(
                    "Embedding model loaded",
                    extra={"model": self._model_name},
                )
        return self._model

    def embed_text(self, text: str) -> Vector:
        """Return a 384-dim embedding for a single text string."""
        model = self._load_model()
        # sentence_transformers encode returns a numpy array; convert to list[float]
        result = model.encode(text, normalize_embeddings=True)  # type: ignore[attr-defined]
        return [float(x) for x in result]

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        """Return a list of 384-dim embeddings. Returns [] for empty input."""
        if not texts:
            return []
        model = self._load_model()
        results = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
        return [[float(x) for x in vec] for vec in results]


# ---------------------------------------------------------------------------
# Lazy process-level singleton
# ---------------------------------------------------------------------------

_provider_instance: BGEEmbeddingProvider | None = None
_provider_lock = threading.Lock()


def get_embedding_provider(
    model_name: str = "BAAI/bge-small-en-v1.5",
) -> BGEEmbeddingProvider:
    """Return the process-level singleton BGEEmbeddingProvider.

    Creates it on first call, reuses on subsequent calls.
    The model_name parameter is only used on first initialization.
    """
    global _provider_instance
    with _provider_lock:
        if _provider_instance is None:
            _provider_instance = BGEEmbeddingProvider(model_name=model_name)
    return _provider_instance


def reset_provider_singleton() -> None:
    """Reset the singleton — for testing only. Not for production use."""
    global _provider_instance
    with _provider_lock:
        _provider_instance = None
