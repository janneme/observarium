"""Shared storage abstraction used by data_prep and server.

Backends: Local (filesystem) and S3. Select via environment `STORAGE`.
This module is located under `python_lib/storage` per project convention.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

# boto3 is optional at module import time; keep a module-level name so tests
# can monkeypatch `python_lib.storage.backend.boto3` before S3Backend is used.
try:
    import boto3  # type: ignore
    from botocore.config import Config as BotocoreConfig  # type: ignore
except Exception:  # pragma: no cover - imported in tests via monkeypatch
    boto3 = None  # type: ignore
    BotocoreConfig = None  # type: ignore

STORAGE = os.environ.get("STORAGE", "local").lower()


def _repo_root() -> Path:
    # backend.py lives at python_lib/storage/backend.py → parents[2] is repo root
    return Path(__file__).resolve().parents[2]


class Backend:
    def read_bytes(self, key: str) -> bytes:
        raise NotImplementedError()

    def write_bytes(self, key: str, data: bytes) -> None:
        raise NotImplementedError()

    def read_json(self, key: str) -> Any:
        return json.loads(self.read_bytes(key).decode("utf-8"))

    def write_json(self, key: str, obj: Any) -> None:
        self.write_bytes(key, json.dumps(obj).encode("utf-8"))

    def exists(self, key: str) -> bool:
        raise NotImplementedError()

    def get_hash(self, key: str) -> str | None:
        """Return a stable content identifier for `key` in the backend.

        For local backend this is SHA-256 hex; for S3 this is the ETag string
        (unquoted). Return None when the object is not present.
        """
        raise NotImplementedError()

    def generate_presigned_put(self, key: str, expires: int = 300) -> str:
        """Return a URL clients can PUT to."""
        raise NotImplementedError()

    def generate_presigned_get(self, key: str, expires: int = 300) -> str:
        """Return a URL clients can GET (download) from."""
        raise NotImplementedError()

    def list_keys(self, prefix: str) -> list[str]:
        """Return all keys in the backend whose name starts with `prefix`."""
        raise NotImplementedError()

    def local_file_path(self, key: str) -> Path | None:
        """Return a pathlib.Path for local backends; None for remote backends."""
        raise NotImplementedError

    def get_location(self, key: str) -> str:
        """Return a human-readable storage location for `key`.

        Examples:
        - local backend: `/abs/path/to/observatorium/objects.zip`
        - s3 backend: `s3://bucket/objects.zip`
        """
        raise NotImplementedError()


class LocalBackend(Backend):
    def __init__(self, base: Path | None = None):
        root = _repo_root()
        # Store data under repository-root/storage (gitignored)
        self.base = (Path(base) if base is not None else root / "storage").resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return (self.base / key).resolve()

    def read_bytes(self, key: str) -> bytes:
        p = self._path(key)
        with p.open("rb") as fh:
            return fh.read()

    def write_bytes(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as fh:
            fh.write(data)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def get_hash(self, key: str) -> str | None:
        p = self._path(key)
        if not p.exists():
            return None
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def generate_presigned_put(self, key: str, expires: int = 300) -> str:
        target = self._path(key)
        return f"file://{str(target)}"

    def generate_presigned_get(self, key: str, expires: int = 300) -> str:
        base_url = os.environ.get("LOCAL_SERVER_URL", "http://localhost:8787")
        return f"{base_url}/local-storage/{key}"

    def local_file_path(self, key: str):
        """Return the filesystem Path for key (overrides base class None)."""
        return self._path(key)

    def list_keys(self, prefix: str) -> list[str]:
        results = []
        for p in sorted(self.base.glob("**/*")):
            if p.is_file():
                key = str(p.relative_to(self.base))
                if key.startswith(prefix):
                    results.append(key)
        return results

    def get_location(self, key: str) -> str:
        return str(self._path(key))


class S3Backend(Backend):
    def __init__(self, bucket: str, region: str | None = None):
        if boto3 is None or BotocoreConfig is None:
            raise RuntimeError("boto3 must be available for S3 backend")

        self.bucket = bucket
        self.region = region
        # Use the regional endpoint with virtual-hosted style so presigned URLs
        # resolve to bucket.s3.eu-central-1.amazonaws.com — no 307 redirect,
        # and S3 CORS headers are returned.  Setting only endpoint_url without
        # addressing_style defaults boto3 to path-style, which is deprecated
        # and S3 does not return CORS headers for path-style requests.
        endpoint_url = f"https://s3.{region}.amazonaws.com" if region else None
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=BotocoreConfig(s3={"addressing_style": "virtual"}),
        )

    def read_bytes(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        body = obj["Body"]
        data = body.read() if hasattr(body, "read") else body
        return data

    def write_bytes(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def get_hash(self, key: str) -> str | None:
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            etag = head.get("ETag")
            if isinstance(etag, str) and etag.startswith('"') and etag.endswith('"'):
                etag = etag[1:-1]
            return etag
        except Exception:
            return None

    def generate_presigned_put(self, key: str, expires: int = 300) -> str:
        return self.client.generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )

    def generate_presigned_get(self, key: str, expires: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )

    def list_keys(self, prefix: str) -> list[str]:
        keys = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def get_location(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"


# Cached backend
_BACKEND: Backend | None = None


def get_backend() -> Backend:
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    if STORAGE == "s3":
        bucket = os.environ.get("DATA_BUCKET")
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not bucket:
            raise RuntimeError("DATA_BUCKET must be set for S3 storage")
        _BACKEND = S3Backend(bucket=bucket, region=region)
    else:
        _BACKEND = LocalBackend()
    return _BACKEND


# Convenience wrappers
def read_bytes(key: str) -> bytes:
    return get_backend().read_bytes(key)


def write_bytes(key: str, data: bytes) -> None:
    return get_backend().write_bytes(key, data)


def read_json(key: str) -> Any:
    return get_backend().read_json(key)


def write_json(key: str, obj: Any) -> None:
    return get_backend().write_json(key, obj)


def exists(key: str) -> bool:
    return get_backend().exists(key)


def get_hash(key: str) -> str | None:
    return get_backend().get_hash(key)


def generate_presigned_put(key: str, expires: int = 300) -> str:
    return get_backend().generate_presigned_put(key, expires)


def generate_presigned_get(key: str, expires: int = 300) -> str:
    return get_backend().generate_presigned_get(key, expires)


def list_keys(prefix: str) -> list[str]:
    return get_backend().list_keys(prefix)
