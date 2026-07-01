"""Unit tests for StorageBackend protocol and LocalStorage implementation.

Tests:
  - test_storage_backend_protocol_substitutable — runtime_checkable isinstance check (AC-BEHAV-B09)
  - test_local_storage_save_read_delete         — full round-trip via tmp_path
  - test_local_storage_path_traversal_rejected  — ValueError on "../" key
  - test_local_storage_read_missing_raises      — FileNotFoundError on unknown key
"""

from __future__ import annotations

import pytest

from app.storage.base import StorageBackend
from app.storage.local_storage import LocalStorage  # noqa: F401 (used implicitly)

# ---------------------------------------------------------------------------
# Stub for protocol structural-subtyping test
# ---------------------------------------------------------------------------


class _StubStorage:
    """Minimal in-memory implementation satisfying the StorageBackend protocol."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self._store[key] = data

    def read(self, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(key)
        return self._store[key]

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_storage_backend_protocol_substitutable() -> None:
    """_StubStorage satisfies the StorageBackend protocol (AC-BEHAV-B09).

    runtime_checkable allows isinstance() without explicit inheritance.
    """
    stub = _StubStorage()
    assert isinstance(stub, StorageBackend), (
        "_StubStorage should be recognized as a StorageBackend via runtime_checkable"
    )


def test_local_storage_save_read_delete(tmp_path: pytest.fixture) -> None:  # type: ignore[type-arg]
    """LocalStorage round-trip: save → read → delete."""
    storage = LocalStorage(tmp_path / "store")
    key = "test-key.bin"
    data = b"hello world"

    storage.save(key, data)
    assert storage.read(key) == data

    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.read(key)


def test_local_storage_path_traversal_rejected(tmp_path: pytest.fixture) -> None:  # type: ignore[type-arg]
    """Path traversal attempt via '../../etc/passwd' key raises ValueError."""
    storage = LocalStorage(tmp_path / "store")
    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        storage.save("../../etc/passwd", b"evil")


def test_local_storage_read_missing_raises(tmp_path: pytest.fixture) -> None:  # type: ignore[type-arg]
    """Reading a non-existent key raises FileNotFoundError."""
    storage = LocalStorage(tmp_path / "store")
    with pytest.raises(FileNotFoundError):
        storage.read("does-not-exist.pdf")
