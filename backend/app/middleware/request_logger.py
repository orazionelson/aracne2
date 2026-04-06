import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

logger = structlog.get_logger()


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        request.state.request_id = request_id

        response: Response = await call_next(request)  # type: ignore[arg-type]

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Skip health endpoint in production to reduce log noise
        skip = request.url.path == "/api/v1/health" and not settings.is_development
        if not skip:
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                ip=request.headers.get(
                    "X-Forwarded-For",
                    request.client.host if request.client else "unknown",
                ),
            )

        response.headers["X-Request-ID"] = request_id
        return response
