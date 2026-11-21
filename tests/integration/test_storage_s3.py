"""S3 backend against a real S3-compatible server (MinIO in development and CI)."""

from __future__ import annotations

import io
import uuid

import pytest

from tests.conftest import require_env
from via_api.storage import ObjectNotFoundError, S3Storage, StorageError, revision_object_key


@pytest.fixture
def s3() -> S3Storage:
    return S3Storage(
        bucket=f"via-test-{uuid.uuid4().hex[:12]}",
        endpoint_url=require_env("VIA_TEST_S3_ENDPOINT"),
        region="us-east-1",
        access_key=require_env("VIA_TEST_S3_ACCESS_KEY"),
        secret_key=require_env("VIA_TEST_S3_SECRET_KEY"),
        auto_create_bucket=True,
    )


def test_bucket_is_created_on_check_and_objects_round_trip(s3):
    s3.check()  # creates the bucket
    key = revision_object_key(uuid.uuid4(), uuid.uuid4(), "source")
    info = s3.put(key, io.BytesIO(b"(kicad_pcb)"), content_type="application/octet-stream")
    assert (info.size_bytes, info.content_type) == (11, "application/octet-stream")
    assert s3.get(key) == b"(kicad_pcb)"
    assert s3.exists(key)
    s3.delete(key)
    assert not s3.exists(key)
    with pytest.raises(ObjectNotFoundError):
        s3.get(key)
    s3.delete(key)  # idempotent


def test_bad_credentials_fail_the_health_check():
    bad = S3Storage(
        bucket="via-designs",
        endpoint_url=require_env("VIA_TEST_S3_ENDPOINT"),
        region="us-east-1",
        access_key="wrong",
        secret_key="wrong-secret-key",
    )
    with pytest.raises(StorageError) as info:
        bad.check()
    assert "wrong-secret-key" not in str(info.value)


def test_missing_bucket_without_auto_create_fails(s3):
    s3.auto_create_bucket = False
    with pytest.raises(StorageError, match="not accessible"):
        s3.check()
