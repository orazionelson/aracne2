from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# Applied to: POST /auth/login, POST /auth/register, POST /auth/password/change
STRICT_LIMIT = "10/minute"
GLOBAL_LIMIT = "200/minute"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please try again later.",
            }
        },
        headers={
            "Retry-After": str(exc.retry_after) if hasattr(exc, "retry_after") else "60"
        },
    )
