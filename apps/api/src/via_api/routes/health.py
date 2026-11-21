"""Liveness and readiness probes."""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from via_api import __version__
from via_api.db import alembic_config, get_db
from via_api.redis_client import get_redis
from via_api.storage import StorageBackend, get_storage

router = APIRouter(prefix="/health", tags=["health"])


class CheckStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class LivenessResponse(BaseModel):
    status: CheckStatus
    version: str


class CheckResult(BaseModel):
    status: CheckStatus
    latency_ms: float
    #: Short, non-sensitive explanation; never contains credentials or hostnames.
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: CheckStatus
    version: str
    checks: dict[str, CheckResult]


def _timed(fn: Callable[[], str | None]) -> CheckResult:
    start = time.perf_counter()
    try:
        detail = fn()
        status = CheckStatus.OK
    except Exception as exc:  # report, never raise, from a probe
        detail = type(exc).__name__
        status = CheckStatus.ERROR
    return CheckResult(status=status, latency_ms=round((time.perf_counter() - start) * 1000, 2), detail=detail)


def expected_migration_head() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


@router.get("", response_model=LivenessResponse, summary="Liveness: the process is up")
def liveness() -> LivenessResponse:
    return LivenessResponse(status=CheckStatus.OK, version=__version__)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
    summary="Readiness: database (with migration state), Redis and object storage",
)
def readiness(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
) -> ReadinessResponse:
    def check_db() -> str:
        db.execute(text("SELECT 1"))
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        head = expected_migration_head()
        if current != head:
            raise RuntimeError("MigrationsPending")
        return f"migrations at {current}"

    def check_redis() -> None:
        if not redis.ping():
            raise RuntimeError("NoPong")

    def check_storage() -> str:
        storage.check()
        return storage.name

    checks = {"database": _timed(check_db), "redis": _timed(check_redis), "storage": _timed(check_storage)}
    if checks["database"].status == CheckStatus.ERROR:
        db.rollback()
    ok = all(c.status == CheckStatus.OK for c in checks.values())
    if not ok:
        response.status_code = 503
    return ReadinessResponse(status=CheckStatus.OK if ok else CheckStatus.ERROR, version=__version__, checks=checks)
