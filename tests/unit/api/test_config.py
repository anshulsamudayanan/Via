import pytest
from pydantic import ValidationError

from via_api.config import Settings


def test_cors_origins_from_comma_separated_env(monkeypatch):
    monkeypatch.setenv("VIA_CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings().cors_origins == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize("secret", ["change-me", "short-but-not-default"])
def test_production_rejects_weak_secret_key(secret):
    with pytest.raises(ValidationError, match="VIA_SECRET_KEY"):
        Settings(env="production", secret_key=secret)


def test_production_rejects_wildcard_cors_and_bucket_autocreate():
    strong = "x" * 40
    with pytest.raises(ValidationError, match="CORS"):
        Settings(env="production", secret_key=strong, cors_origins=["*"])
    with pytest.raises(ValidationError, match="AUTO_CREATE"):
        Settings(env="production", secret_key=strong, s3_auto_create_bucket=True)


def test_secrets_are_not_rendered_in_repr():
    s = Settings(secret_key="super-secret-value-that-is-long-enough", s3_secret_key="minio-secret")
    assert "super-secret-value" not in repr(s)
    assert "minio-secret" not in repr(s)
