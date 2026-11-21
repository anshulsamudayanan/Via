"""``via-api`` command: run migrations, serve the API, check dependencies.

via-api migrate          # alembic upgrade head
via-api serve [--reload] # uvicorn on 0.0.0.0:8000
via-api check            # readiness checks from the command line (exit 1 on failure)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _migrate() -> int:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(ALEMBIC_INI)), "head")
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
    serve = sub.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container entrypoint
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    sub.add_parser("check", help="run readiness checks")
    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _migrate()
    if args.command == "serve":
        return _serve(args.host, args.port, args.reload)
    return _check()


if __name__ == "__main__":
    sys.exit(main())
