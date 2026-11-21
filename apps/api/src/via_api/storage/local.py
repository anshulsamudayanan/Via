"""Local filesystem backend for tests and single-machine development."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from via_api.storage.base import ObjectInfo, ObjectNotFoundError, StorageBackend, StorageError, validate_key


class LocalStorage(StorageBackend):
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # defence in depth; validate_key already forbids '..'
            raise StorageError(f"Key escapes storage root: {key}")
        return path

    def put(self, key: str, data: BinaryIO | bytes, *, content_type: str, size: int | None = None) -> ObjectInfo:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as out:
                if isinstance(data, bytes):
                    out.write(data)
                else:
                    shutil.copyfileobj(data, out)
            os.replace(tmp, path)  # atomic within a filesystem
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        path.with_name(path.name + ".meta").write_text(json.dumps({"content_type": content_type}))
        return self.stat(key)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        return path.read_bytes()

    def stat(self, key: str) -> ObjectInfo:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        meta = path.with_name(path.name + ".meta")
        content_type = json.loads(meta.read_text()).get("content_type") if meta.is_file() else None
        return ObjectInfo(key=key, size_bytes=path.stat().st_size, content_type=content_type)

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".meta").unlink(missing_ok=True)

    def check(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".health"
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError as exc:
            raise StorageError(f"Local storage not writable: {exc.strerror}") from exc
