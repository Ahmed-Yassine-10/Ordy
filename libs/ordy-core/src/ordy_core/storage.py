"""Object storage port (doc 01 §4.7). Blobs are keyed ``t/{restaurant_id}/…``.

A local-filesystem implementation backs dev; an S3 implementation (boto3, optional)
backs staging/prod. Both satisfy ``ObjectStore``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str: ...
    def get_bytes(self, key: str) -> bytes: ...
    def put_json(self, key: str, obj: object) -> str: ...
    def exists(self, key: str) -> bool: ...


class LocalObjectStore:
    """Writes under a base directory. For local dev / tests (MinIO is used in compose)."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)

    def _path(self, key: str) -> Path:
        p = (self._base / key).resolve()
        if not str(p).startswith(str(self._base.resolve())):
            raise ValueError("key escapes storage root")
        return p

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def put_json(self, key: str, obj: object) -> str:
        return self.put_bytes(
            key, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
        )

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


def tenant_prefix(restaurant_id: str, *parts: str) -> str:
    return "/".join(["t", restaurant_id, *parts])
