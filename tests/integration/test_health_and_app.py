"""Health probes, error envelope, security headers and CORS."""

from __future__ import annotations

from fastapi.testclient import TestClient
from redis import Redis

from via_api.main import create_app
from via_api.redis_client import get_redis


def test_liveness(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "0.1.0"}


def test_readiness_checks_database_migrations_redis_and_storage(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {"database", "redis", "storage"}
    assert body["checks"]["database"]["detail"] == "migrations at 0002"
    assert all(c["status"] == "ok" for c in body["checks"].values())


def test_readiness_reports_503_when_redis_is_down(client, app):
    app.dependency_overrides[get_redis] = lambda: Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.5)
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    assert body["checks"]["redis"]["status"] == "error"
    assert body["checks"]["redis"]["detail"] == "ConnectionError"  # class name only, no host details
    assert body["checks"]["database"]["status"] == "ok"


def test_error_envelope_and_request_id(client):
    resp = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "test-request-0001"})
    assert resp.status_code == 404
    assert resp.headers["x-request-id"] == "test-request-0001"
    assert resp.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None, "request_id": "test-request-0001"}
    }


def test_untrusted_request_ids_are_replaced(client):
    resp = client.get("/api/v1/health", headers={"X-Request-ID": "<script>"})
    assert resp.headers["x-request-id"] != "<script>"


def test_method_not_allowed_uses_envelope(client):
    resp = client.post("/api/v1/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "method_not_allowed"


def test_security_headers(client):
    resp = client.get("/api/v1/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["cache-control"] == "no-store"


def test_cors_allows_only_configured_origins(client):
    ok = client.options(
        "/api/v1/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options(
        "/api/v1/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in bad.headers


def test_unhandled_errors_do_not_leak_details(settings):
    app = create_app(settings)

    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    resp = TestClient(app, raise_server_exceptions=False).get("/api/v1/_boom")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "secret" not in resp.text


def test_openapi_lists_versioned_routes(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/v1/health" in paths and "/api/v1/health/ready" in paths
