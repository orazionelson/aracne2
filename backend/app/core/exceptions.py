from dataclasses import dataclass, field


@dataclass
class PlatformException(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, object] = field(default_factory=dict)


class NotFoundError(PlatformException):
    def __init__(self, resource: str, identifier: str = "") -> None:
        label = f"{resource} '{identifier}'" if identifier else resource
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"{label} not found",
            status_code=404,
        )


class ConflictError(PlatformException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)


class AuthenticationError(PlatformException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=401)


class AuthorizationError(PlatformException):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(
            code="INSUFFICIENT_PERMISSIONS",
            message=message,
            status_code=403,
        )


class DomainValidationError(PlatformException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=422)


class ExternalServiceError(PlatformException):
    def __init__(self, service: str, detail: str = "") -> None:
        super().__init__(
            code="EXTERNAL_SERVICE_ERROR",
            message=f"Service '{service}' unavailable",
            status_code=503,
            details={"service": service, "detail": detail},
        )
