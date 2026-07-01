"""LocalStorage — non-web-served local volume implementation.

MVP storage backend. base_dir must be outside any web-served/static path.
Implements the StorageBackend protocol.
"""

from __future__ import annotations

import pathlib


class LocalStorage:
    """Non-web-served local volume implementation. MVP storage backend."""

    def __init__(self, base_dir: str | pathlib.Path) -> None:
        """base_dir must be outside any web-served/static path."""
        self._base = pathlib.Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes) -> None:
        """Save bytes under the given key."""
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        """Read bytes for the given key. Raises FileNotFoundError if missing."""
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Storage key not found: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        """Delete the file at the given key. No-op if already deleted."""
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def _resolve(self, key: str) -> pathlib.Path:
        """Resolve key to an absolute path safely within base_dir.

        Prevents path traversal: resolves to real path and verifies it's under base_dir.
        Raises ValueError if the resolved path escapes the base directory.
        """
        resolved = (self._base / key).resolve()
        if not str(resolved).startswith(str(self._base.resolve())):
            raise ValueError(f"Path traversal attempt detected: {key}")
        return resolved
