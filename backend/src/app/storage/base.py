"""StorageBackend Protocol — abstract file storage interface.

Callers depend on this protocol, not on any concrete implementation.
This keeps the repository layer decoupled from the physical storage medium.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Abstract file storage interface. Callers depend on this, not on LocalStorage."""

    def save(self, key: str, data: bytes) -> None:
        """Save bytes under the given key."""
        ...

    def read(self, key: str) -> bytes:
        """Read bytes for the given key. Raises FileNotFoundError if missing."""
        ...

    def delete(self, key: str) -> None:
        """Delete the file at the given key. No-op if already deleted."""
        ...
