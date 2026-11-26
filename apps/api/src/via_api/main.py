"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from via_api import __version__
from via_api.config import Settings, get_settings
from via_api.errors import ErrorResponse, install_error_handlers
from via_api.middleware import CSRFMiddleware, RequestContextMiddleware, UploadSizeMiddleware
from via_api.routes import (
    activity,
    ai,
    analysis,
    auth,
    browse,
    changes,
    designs,
    files,
    health,
    intelligence,
    optimization,
    organizations,
    pcb,
    projects,
    users,
)

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    docs = settings.enable_docs
    app = FastAPI(
        title="VIA API",
        version=__version__,
        description="VIA engineering platform API. All endpoints are versioned under /api/v1.",
        openapi_url="/api/openapi.json" if docs else None,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        responses={
            422: {"model": ErrorResponse, "description": "Validation error"},
            500: {"model": ErrorResponse, "description": "Internal error"},
        },
    )
    # Starlette runs the last-added middleware first: request context wraps CSRF.
    app.add_middleware(UploadSizeMiddleware, paths={pcb.IMPORT_PATH}, max_bytes=settings.max_upload_bytes)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-VIA-Request"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    install_error_handlers(app)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(health.router)
    v1.include_router(auth.router)
    v1.include_router(users.router)
    v1.include_router(organizations.router)
    v1.include_router(projects.router)
    v1.include_router(activity.router)
    v1.include_router(pcb.router)
    v1.include_router(designs.router)
    v1.include_router(files.router)
    v1.include_router(ai.router)
    v1.include_router(analysis.router)
    v1.include_router(intelligence.router)
    v1.include_router(optimization.router)
    v1.include_router(changes.router)
    v1.include_router(browse.router)
    app.include_router(v1)
    return app
