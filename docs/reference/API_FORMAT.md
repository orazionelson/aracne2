# Aracne2 — API Response Format Reference
# Reference only. All API responses must conform to this specification.

## Response shapes

```jsonc
// Paginated list
{
  "data": [ /* array of objects */ ],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total": 142,
    "total_pages": 15
  }
}

// Single resource
{ "data": { /* object */ } }

// Error — all codes in SCREAMING_SNAKE_CASE
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "User not found",
    "details": {}   // optional, only in development environment
  }
}
```

## Pydantic schemas (app/schemas/common.py)

```python
from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")

class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: PaginationMeta

class DataResponse(BaseModel, Generic[T]):
    data: T

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = {}

class ErrorResponse(BaseModel):
    error: ErrorDetail

class HealthService(BaseModel):
    status: str          # "ok" | "error"
    detail: str | None = None   # only in development

class HealthResponse(BaseModel):
    status: str          # "healthy" | "degraded"
    version: str
    environment: str
    services: dict[str, HealthService]
```

## HTTP status codes

| Code | When to use                                      |
|------|--------------------------------------------------|
| 200  | Successful read or update                        |
| 201  | Successful creation                              |
| 204  | Successful deletion (no body)                    |
| 400  | Malformed input (syntax errors, missing fields)  |
| 401  | Unauthenticated (missing or invalid token)       |
| 403  | Authenticated but insufficient permissions       |
| 404  | Resource not found                               |
| 409  | Conflict (duplicate, constraint violation)       |
| 422  | Semantic validation error (valid syntax, bad logic) |
| 429  | Rate limit exceeded                              |
| 500  | Unhandled internal server error                  |
| 503  | External service (eXist-db, SMTP) unavailable    |

## Error code conventions

- Always SCREAMING_SNAKE_CASE: `USER_NOT_FOUND`, `EMAIL_ALREADY_EXISTS`
- Domain prefix where useful: `AUTH_INVALID_CREDENTIALS`, `ACL_INSUFFICIENT_PERMISSIONS`
- `details` field: only populated in `ENVIRONMENT=development`. Empty dict `{}` in production.
