"""Shared test configuration.

Integration tests need real services, configured with environment variables:

    VIA_TEST_DATABASE_URL   postgresql+psycopg://via:via@localhost:5432/via_test  (database is reset!)
    VIA_TEST_REDIS_URL      redis://localhost:6379/15
    VIA_TEST_S3_ENDPOINT    http://localhost:9000   (+ VIA_TEST_S3_ACCESS_KEY / VIA_TEST_S3_SECRET_KEY)

Locally, a missing service makes the dependent tests *skip* with the reason in
the summary (``-ra``). In CI (``CI=true``) a missing service is a hard failure,
so nothing is silently skipped where it matters.
"""

from __future__ import annotations

import os

import pytest


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    message = f"{name} is not set (see tests/conftest.py)"
    if os.environ.get("CI", "").lower() in {"1", "true", "yes"}:
        pytest.fail(f"{message}; required in CI", pytrace=False)
    pytest.skip(message)
