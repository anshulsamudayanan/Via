"""Request ID, access logging and security headers."""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger("via_api.access")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/v1/"):
            response.headers.setdefault("Cache-Control", "no-store")
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )
        return response


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-via-request"


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject cross-site state-changing requests.

    Browsers cannot attach custom headers to cross-site form posts or simple
    requests, and CORS blocks them for scripts from other origins. Requiring
    ``X-VIA-Request: 1`` on every unsafe ``/api/v1`` request therefore stops
    CSRF for cookie sessions (including login CSRF). Bearer-token clients are
    exempt: their credential is not sent automatically by a browser.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method in _UNSAFE_METHODS
            and request.url.path.startswith("/api/v1/")
            and not request.headers.get("authorization", "").lower().startswith("bearer ")
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "csrf_failed",
                        "message": "Missing X-VIA-Request header.",
                        "details": None,
                        "request_id": getattr(request.state, "request_id", None),
                    }
                },
            )
        return await call_next(request)


#: Multipart framing + form fields allowance on top of the file size limit.
MULTIPART_OVERHEAD = 1024 * 1024


class UploadSizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized uploads before the body is read.

    FastAPI parses multipart bodies before the route runs, so the size check
    must happen here. The route re-checks the actual bytes read.
    """

    def __init__(self, app: ASGIApp, paths: set[str], max_bytes: int) -> None:
        super().__init__(app)
        self.paths = paths
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "POST" and request.url.path in self.paths:
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                return _error(request, 411, "length_required", "Uploads must include a Content-Length header.")
            if int(length) > self.max_bytes + MULTIPART_OVERHEAD:
                mb = self.max_bytes // (1024 * 1024)
                return _error(request, 413, "payload_too_large", f"The file is larger than the {mb} MB limit.")
        return await call_next(request)


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": None,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
