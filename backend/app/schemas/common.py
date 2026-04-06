from typing import Generic, TypeVar

from pydantic import BaseModel

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
    details: dict[str, object] = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthService(BaseModel):
    status: str  # "ok" | "error"
    detail: str | None = None  # only in development


class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded"
    version: str
    environment: str
    services: dict[str, HealthService]
