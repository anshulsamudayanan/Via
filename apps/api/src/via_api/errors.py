"""Consistent error envelope for every API error.

Every non-2xx response has the shape::

    {"error": {"code": "not_found", "message": "Project not found", "details": null, "request_id": "..."}}

Unexpected exceptions are logged with the request id and returned as a generic
500. Internal details never reach the client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("via_api.errors")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class APIError(Exception):
    """Raise from routes/services to return a structured error."""

    def __init__(self, status_code: int, code: str, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def not_found(resource: str) -> APIError:
    return APIError(404, "not_found", f"{resource} not found")


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
}


def _response(request: Request, status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, details=details, request_id=getattr(request.state, "request_id", None)
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError) -> JSONResponse:
        return _response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ").capitalize()
        return _response(request, exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(err.get("loc", ())), "message": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors()
        ]
        return _response(request, 422, "validation_error", "Request validation failed", details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", extra={"request_id": getattr(request.state, "request_id", None)})
        return _response(request, 500, "internal_error", "An internal error occurred")


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses=`` entry documenting the error envelope for these statuses."""
    return {code: {"model": ErrorResponse} for code in status_codes}
