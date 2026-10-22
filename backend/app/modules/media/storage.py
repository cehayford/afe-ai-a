"""File storage split by sensitivity (Statement §8.6).

"public" holds processed listing photos, served to everyone (CloudFront in production).
"private" holds Ghana Card and ownership documents: never served by URL, read only by the
API for a reviewer, with every read logged.

Two backends behind one interface, picked by AFE_STORAGE_BACKEND:
- "local": folders on disk, for development and tests.
- "s3": the afe-media-public and afe-kyc-private buckets. Encryption at rest (KMS on the
  private bucket), versioning and public-access blocks are bucket settings managed in
  Terraform (infra/terraform), not per-object flags here.
"""

import mimetypes
import secrets
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from app.config import get_settings

Bucket = Literal["public", "private"]


def _new_key(prefix: str, suffix: str) -> str:
    return f"{prefix}/{datetime.now():%Y/%m}/{secrets.token_hex(12)}{suffix}"


def _public_url(key: str) -> str:
    return f"{get_settings().media_url.rstrip('/')}/{key}"


class Storage(Protocol):
    def save(self, bucket: Bucket, prefix: str, data: bytes, suffix: str) -> str: ...
    def read(self, bucket: Bucket, key: str) -> bytes: ...
    def public_url(self, key: str) -> str: ...


class LocalStorage:
    def _root(self, bucket: Bucket) -> Path:
        s = get_settings()
        return s.media_root if bucket == "public" else s.private_media_root

    def save(self, bucket: Bucket, prefix: str, data: bytes, suffix: str) -> str:
        """Store bytes under an unguessable key and return the key."""
        key = _new_key(prefix, suffix)
        path = self.path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, bucket: Bucket, key: str) -> bytes:
        path = self.path(bucket, key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def path(self, bucket: Bucket, key: str) -> Path:
        root = self._root(bucket).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Key escapes the storage root")
        return path

    def public_url(self, key: str) -> str:
        return _public_url(key)


class S3Storage:
    def __init__(self):
        import boto3  # only needed when the S3 backend is in use

        s = get_settings()
        self._buckets = {"public": s.s3_bucket_public, "private": s.s3_bucket_private}
        self._client = boto3.client("s3", region_name=s.s3_region, endpoint_url=s.s3_endpoint_url or None)

    def save(self, bucket: Bucket, prefix: str, data: bytes, suffix: str) -> str:
        key = _new_key(prefix, suffix)
        content_type = mimetypes.guess_type(f"x{suffix}")[0] or "application/octet-stream"
        extra = {"CacheControl": "public, max-age=31536000, immutable"} if bucket == "public" else {}
        self._client.put_object(Bucket=self._buckets[bucket], Key=key, Body=data, ContentType=content_type, **extra)
        return key

    def read(self, bucket: Bucket, key: str) -> bytes:
        try:
            obj = self._client.get_object(Bucket=self._buckets[bucket], Key=key)
        except self._client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(key) from exc
        return obj["Body"].read()

    def public_url(self, key: str) -> str:
        return _public_url(key)


_local = LocalStorage()
_s3: S3Storage | None = None


def get_storage() -> Storage:
    global _s3
    if get_settings().storage_backend == "s3":
        if _s3 is None:
            _s3 = S3Storage()
        return _s3
    return _local


class _StorageProxy:
    """`storage.save(...)` etc. go to whichever backend settings select at call time."""

    def __getattr__(self, name):
        return getattr(get_storage(), name)


storage: Storage = _StorageProxy()  # type: ignore[assignment]


def reset_storage() -> None:
    """Forget the cached S3 client (tests, or after changing settings)."""
    global _s3
    _s3 = None
