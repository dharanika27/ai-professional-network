"""Storage package — StorageBackend protocol and LocalStorage implementation."""

from app.storage.base import StorageBackend
from app.storage.local_storage import LocalStorage

__all__ = ["StorageBackend", "LocalStorage"]
