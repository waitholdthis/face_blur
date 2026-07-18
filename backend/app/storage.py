"""Pluggable object storage with signed-URL access.

Two backends:

* ``local`` (default) — filesystem under ``STORAGE_LOCAL_DIR``. Objects are
  served back through the API's ``/api/v1/assets`` route using short-lived
  HMAC-signed URLs, emulating S3 pre-signed URLs so nothing is world-readable.
* ``s3`` — real S3 (or S3-compatible) buckets using boto3 pre-signed URLs.

The raw bucket holds unblurred originals (private); the processed bucket holds
anonymized, distributable renders.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import quote, urlencode

from .config import settings

RAW_BUCKET = settings.s3_raw_bucket
PROCESSED_BUCKET = settings.s3_processed_bucket


class StorageBackend(ABC):
    @abstractmethod
    def save(self, bucket: str, key: str, data: bytes) -> str: ...

    @abstractmethod
    def load(self, bucket: str, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool: ...

    @abstractmethod
    def delete(self, bucket: str, key: str) -> None: ...

    @abstractmethod
    def url(self, bucket: str, key: str, expires: Optional[int] = None) -> str: ...


def _sign(message: str) -> str:
    digest = hmac.new(settings.jwt_secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def verify_asset_token(bucket: str, key: str, expires: str, token: str) -> bool:
    """Validate a local signed-URL token (constant-time, expiry-checked)."""
    try:
        if int(expires) < int(time.time()):
            return False
    except (TypeError, ValueError):
        return False
    expected = _sign(f"{bucket}/{key}:{expires}")
    return hmac.compare_digest(expected, token)


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, bucket: str, key: str, *, create_parent: bool = False) -> str:
        bucket_root = os.path.abspath(os.path.join(self.base_dir, bucket))
        path = os.path.abspath(os.path.join(bucket_root, key))
        try:
            contained = os.path.commonpath([bucket_root, path]) == bucket_root
        except ValueError:
            contained = False
        if not contained:
            raise ValueError("Storage key escapes its bucket")
        if create_parent:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def save(self, bucket: str, key: str, data: bytes) -> str:
        path = self._path(bucket, key, create_parent=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return f"{bucket}/{key}"

    def load(self, bucket: str, key: str) -> bytes:
        with open(self._path(bucket, key), "rb") as fh:
            return fh.read()

    def exists(self, bucket: str, key: str) -> bool:
        return os.path.exists(self._path(bucket, key))

    def delete(self, bucket: str, key: str) -> None:
        path = self._path(bucket, key)
        try:
            os.remove(path)
        except FileNotFoundError:
            return

    def url(self, bucket: str, key: str, expires: Optional[int] = None) -> str:
        ttl = expires or settings.s3_presign_expiry_seconds
        exp = str(int(time.time()) + ttl)
        token = _sign(f"{bucket}/{key}:{exp}")
        query = urlencode({"exp": exp, "token": token})
        encoded_bucket = quote(bucket, safe="")
        encoded_key = quote(key, safe="/")
        return f"{settings.public_base_url}/api/v1/assets/{encoded_bucket}/{encoded_key}?{query}"


class S3Storage(StorageBackend):  # pragma: no cover - exercised only with real S3
    def __init__(self) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def save(self, bucket: str, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=bucket, Key=key, Body=data)
        return f"{bucket}/{key}"

    def load(self, bucket: str, key: str) -> bytes:
        obj = self._client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    def exists(self, bucket: str, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)

    def url(self, bucket: str, key: str, expires: Optional[int] = None) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires or settings.s3_presign_expiry_seconds,
        )


_backend: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        if settings.storage_backend == "s3":
            _backend = S3Storage()
        else:
            _backend = LocalStorage(settings.storage_local_dir)
    return _backend


def reset_storage_for_tests(base_dir: str) -> None:
    """Point storage at a fresh directory (used by the test-suite)."""
    global _backend
    _backend = LocalStorage(base_dir)
