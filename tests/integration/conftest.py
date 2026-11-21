from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import require_env
from via_api.config import Settings, StorageBackendName, get_settings
from via_api.db import get_db
from via_api.main import create_app
from via_api.redis_client import get_redis
from via_api.storage import LocalStorage, get_storage

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "apps" / "api" / "alembic.ini"


def alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


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
def client(settings: Settings, db: Session) -> Iterator[TestClient]:
    from redis import Redis

    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_redis] = lambda: Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    app.dependency_overrides[get_storage] = lambda: LocalStorage(settings.local_storage_path)
    with TestClient(app) as c:
        yield c


def new_id() -> uuid.UUID:
    return uuid.uuid4()
