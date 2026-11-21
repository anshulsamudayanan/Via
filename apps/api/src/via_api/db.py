"""Database engine, session factory and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from via_api.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def alembic_config(database_url: str | None = None) -> AlembicConfig:
    """Alembic config for the migrations bundled in the ``via_api.migrations`` package.

    Works the same from a source checkout and from an installed wheel (Docker).
    """
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", "via_api:migrations")
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg
