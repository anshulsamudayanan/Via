"""Object storage abstraction (S3-compatible or local filesystem)."""

from __future__ import annotations

from functools import lru_cache

from via_api.config import StorageBackendName, get_settings
from via_api.storage.base import (
    InvalidKeyError,
    ObjectInfo,
    ObjectNotFoundError,
    StorageBackend,
    StorageError,
    revision_object_key,
    validate_key,
)
from via_api.storage.local import LocalStorage
from via_api.storage.s3 import S3Storage


@lru_cache
def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == StorageBackendName.LOCAL:
        return LocalStorage(settings.local_storage_path)
    return S3Storage.from_settings(settings)


__all__ = [
    "InvalidKeyError",
    "LocalStorage",
    "ObjectInfo",
    "ObjectNotFoundError",
    "S3Storage",
    "StorageBackend",
    "StorageError",
    "get_storage",
    "revision_object_key",
    "validate_key",
]
