from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import require_env
from via_api.config import Settings, StorageBackendName, get_settings
from via_api.db import alembic_config, get_db
from via_api.deps import get_email_sender
from via_api.emails import MemoryEmailSender
from via_api.main import create_app
from via_api.redis_client import get_redis
from via_api.storage import LocalStorage, get_storage


def reset_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture(scope="session")
def database_url() -> str:
    return require_env("VIA_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    """A database migrated to head once per session (schema reset first)."""
    engine = create_engine(database_url)
    reset_schema(engine)
    command.upgrade(alembic_config(database_url), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test."""
    conn = migrated_engine.connect()
    trans = conn.begin()
    session = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        database_url=database_url,
        redis_url=require_env("VIA_TEST_REDIS_URL"),
        storage_backend=StorageBackendName.LOCAL,
        local_storage_path=tmp_path / "storage",
        cors_origins=["http://localhost:3000"],
    )


@pytest.fixture
def test_redis(settings: Settings):
    from redis import Redis

    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    redis.flushdb()  # fresh rate-limit counters for every test (dedicated test DB index)
    return redis


@pytest.fixture
def mailer() -> MemoryEmailSender:
    return MemoryEmailSender()


@pytest.fixture
def app(settings: Settings, db: Session, test_redis, mailer: MemoryEmailSender):
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_redis] = lambda: test_redis
    app.dependency_overrides[get_storage] = lambda: LocalStorage(settings.local_storage_path)
    app.dependency_overrides[get_email_sender] = lambda: mailer
    return app


@pytest.fixture
def make_client(app) -> Iterator[Callable[..., TestClient]]:
    """Factory for independent clients (separate cookie jars = separate users)."""
    clients: list[TestClient] = []

    def factory(csrf: bool = True) -> TestClient:
        c = TestClient(app, headers={"X-VIA-Request": "1"} if csrf else {})
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


PASSWORD = "correct horse battery"


def register(client: TestClient, email: str, name: str = "Test User", password: str = PASSWORD) -> dict:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": name})
    assert resp.status_code == 201, resp.json()
    return resp.json()


def new_id() -> uuid.UUID:
    return uuid.uuid4()
