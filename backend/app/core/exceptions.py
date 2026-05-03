from dataclasses import dataclass, field


@dataclass
class PlatformException(Exception):  # noqa: N818
    code: str
    message: str
    status_code: int = 400
    details: dict[str, object] = field(default_factory=dict)


class NotFoundError(PlatformException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(code="RESOURCE_NOT_FOUND", message=message, status_code=404)


class ConflictError(PlatformException):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(code="CONFLICT", message=message, status_code=409)


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


class DocumentBusyError(PlatformException):
    """Another writer holds the document advisory lock — retry shortly."""

    def __init__(self, message: str = "Document is busy, retry shortly") -> None:
        super().__init__(code="DOCUMENT_BUSY", message=message, status_code=409)


class ManualVersionsLimitReached(PlatformException):
    """Soft cap on per-document manual versions reached.

    Auto versions (workflow events, rollback) are unlimited; only manual
    "Save version" entries count against the cap, configurable via
    ``system_settings.document_manual_versions_max``.
    """

    def __init__(self, current: int, limit: int) -> None:
        super().__init__(
            code="MANUAL_VERSIONS_LIMIT_REACHED",
            message=(
                f"Manual versions limit reached ({current}/{limit}). "
                "Delete older manual versions before creating a new one."
            ),
            status_code=409,
            details={"current": current, "limit": limit},
        )


class VersionNotPublic(PlatformException):
    """A public ``?version=N`` permalink can only resolve to ``publication``
    rows. Manual / submission / rejection / rollback / creation versions
    must never leak through the public renderer."""

    def __init__(
        self, message: str = "This version is not part of the public history"
    ) -> None:
        super().__init__(
            code="VERSION_NOT_PUBLIC", message=message, status_code=404
        )
