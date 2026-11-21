"""``via-api`` command: run migrations, serve the API, check dependencies.

via-api migrate          # alembic upgrade head
via-api serve [--reload] # uvicorn on 0.0.0.0:8000
via-api check            # readiness checks from the command line (exit 1 on failure)
"""

from __future__ import annotations

import argparse
import json
import sys


def _migrate() -> int:
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    from via_api.config import get_settings
    from via_api.db import alembic_config

    url = get_settings().database_url

    def current() -> str | None:
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                return MigrationContext.configure(conn).get_current_revision()
        finally:
            engine.dispose()

    before = current()
    command.upgrade(alembic_config(url), "head")
    after = current()
    print(
        f"database migrations: {before or 'empty'} -> {after}" if before != after else f"database up to date ({after})"
    )
    return 0


def _init_storage() -> int:
    """Verify object storage; create the bucket only when VIA_S3_AUTO_CREATE_BUCKET=true (dev)."""
    from via_api.storage import StorageError, get_storage

    storage = get_storage()
    try:
        storage.check()
    except StorageError as exc:
        print(f"storage check failed: {exc}", file=sys.stderr)
        return 1
    print(f"storage ok ({storage.name})")
    return 0


def _serve(host: str, port: int, reload: bool) -> int:
    import uvicorn

    from via_api.config import get_settings

    uvicorn.run(
        "via_api.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        proxy_headers=True,
        forwarded_allow_ips=get_settings().forwarded_allow_ips,
    )
    return 0


def _worker(burst: bool) -> int:
    """Run an RQ worker for the import queue (forks one work-horse process per job)."""
    import logging

    from rq import Queue, Worker

    from via_api.config import get_settings
    from via_api.redis_client import get_redis

    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    redis = get_redis()
    worker = Worker([Queue(settings.import_queue_name, connection=redis)], connection=redis)
    worker.work(burst=burst, with_scheduler=False)
    return 0


def _check() -> int:
    from fastapi.testclient import TestClient

    from via_api.main import create_app

    resp = TestClient(create_app()).get("/api/v1/health/ready")
    print(json.dumps(resp.json(), indent=2))
    return 0 if resp.status_code == 200 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="via-api")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("init-storage", help="verify object storage (creates the bucket when auto-create is enabled)")
    serve = sub.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container entrypoint
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    worker = sub.add_parser("worker", help="process background jobs (PCB imports)")
    worker.add_argument("--burst", action="store_true", help="exit when the queue is empty")
    sub.add_parser("check", help="run readiness checks")
    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _migrate()
    if args.command == "init-storage":
        return _init_storage()
    if args.command == "serve":
        return _serve(args.host, args.port, args.reload)
    if args.command == "worker":
        return _worker(args.burst)
    return _check()


if __name__ == "__main__":
    sys.exit(main())
