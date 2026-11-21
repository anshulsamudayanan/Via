"""S3-compatible backend (AWS S3, MinIO, ...)."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from via_api.storage.base import ObjectInfo, ObjectNotFoundError, StorageBackend, StorageError, validate_key

if TYPE_CHECKING:
    from via_api.config import Settings

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str | None,
        secret_key: str | None,
        auto_create_bucket: bool = False,
    ) -> None:
        self.bucket = bucket
        self.auto_create_bucket = auto_create_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=3,
                read_timeout=30,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> S3Storage:
        return cls(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            access_key=settings.s3_access_key.get_secret_value() if settings.s3_access_key else None,
            secret_key=settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else None,
            auto_create_bucket=settings.s3_auto_create_bucket,
        )

    def put(self, key: str, data: BinaryIO | bytes, *, content_type: str, size: int | None = None) -> ObjectInfo:
        validate_key(key)
        body = io.BytesIO(data) if isinstance(data, bytes) else data
        try:
            self._client.upload_fileobj(body, self.bucket, key, ExtraArgs={"ContentType": content_type})
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"S3 put failed for {key}: {exc}") from exc
        return self.stat(key)

    def get(self, key: str) -> bytes:
        validate_key(key)
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND:
                raise ObjectNotFoundError(key) from exc
            raise StorageError(f"S3 get failed for {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"S3 get failed for {key}: {exc}") from exc

    def stat(self, key: str) -> ObjectInfo:
        validate_key(key)
        try:
            resp = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND:
                raise ObjectNotFoundError(key) from exc
            raise StorageError(f"S3 head failed for {key}: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"S3 head failed for {key}: {exc}") from exc
        return ObjectInfo(key=key, size_bytes=int(resp["ContentLength"]), content_type=resp.get("ContentType"))

    def delete(self, key: str) -> None:
        validate_key(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"S3 delete failed for {key}: {exc}") from exc

    def check(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in _NOT_FOUND and self.auto_create_bucket:
                self._create_bucket()
                return
            raise StorageError(f"Bucket '{self.bucket}' not accessible ({code})") from exc
        except BotoCoreError as exc:
            raise StorageError(f"S3 endpoint unreachable: {exc}") from exc

    def _create_bucket(self) -> None:
        try:
            # New S3/MinIO buckets are private by default; no public policy is ever attached.
            self._client.create_bucket(Bucket=self.bucket)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not create bucket '{self.bucket}': {exc}") from exc
