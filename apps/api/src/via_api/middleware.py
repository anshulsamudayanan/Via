"""Request ID, access logging and security headers."""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

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
