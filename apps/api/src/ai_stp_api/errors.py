"""Map errors to the envelope via the foundation registry (SPEC-017 REQ-1706).

Categories map to registered AI_STP_* codes and HTTP statuses through tables, so
handlers carry no magic numbers. An unhandled exception becomes AI_STP_INTERNAL
with no stacktrace or secret in the client output.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_stp_api.envelope import error_response
from ai_stp_foundation.errors import exit_class_for
from ai_stp_platform.logging import get_logger

_log = get_logger("errors")


class ErrorCategory(StrEnum):
    """Client-facing error categories mapped to the code registry."""

    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    AUTH_REQUIRED = "auth_required"
    PERMISSION = "permission"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    DEPENDENCY = "dependency"
    INTERNAL = "internal"
    # A stored object exists but failed its own integrity check. Kept apart from
    # INTERNAL so the condition is separately observable (SPEC-021 REQ-2108).
    CATALOG_INTEGRITY = "catalog_integrity"
    # Device-code poll outcomes share HTTP 400 but keep distinct stable codes.
    AUTHORIZATION_PENDING = "authorization_pending"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    AUTHORIZATION_DECLINED = "authorization_declined"
    PRECONDITION = "precondition"
    DEVICE_REVOKED = "device_revoked"


CATEGORY_CODE: Mapping[ErrorCategory, str] = {
    ErrorCategory.VALIDATION: "AI_STP_VALIDATION_ERROR",
    ErrorCategory.NOT_FOUND: "AI_STP_NOT_FOUND",
    ErrorCategory.AUTH_REQUIRED: "AI_STP_AUTH_REQUIRED",
    ErrorCategory.PERMISSION: "AI_STP_PERMISSION_DENIED",
    ErrorCategory.CONFLICT: "AI_STP_CONFLICT",
    ErrorCategory.RATE_LIMITED: "AI_STP_RATE_LIMITED",
    ErrorCategory.DEPENDENCY: "AI_STP_DEPENDENCY_UNAVAILABLE",
    ErrorCategory.INTERNAL: "AI_STP_INTERNAL",
    ErrorCategory.CATALOG_INTEGRITY: "AI_STP_CATALOG_INTEGRITY",
    ErrorCategory.AUTHORIZATION_PENDING: "AI_STP_AUTHORIZATION_PENDING",
    ErrorCategory.AUTHORIZATION_EXPIRED: "AI_STP_AUTHORIZATION_EXPIRED",
    ErrorCategory.AUTHORIZATION_DECLINED: "AI_STP_AUTHORIZATION_DECLINED",
    ErrorCategory.PRECONDITION: "AI_STP_PRECONDITION_FAILED",
    ErrorCategory.DEVICE_REVOKED: "AI_STP_DEVICE_REVOKED",
}

CATEGORY_STATUS: Mapping[ErrorCategory, HTTPStatus] = {
    ErrorCategory.VALIDATION: HTTPStatus.BAD_REQUEST,
    ErrorCategory.NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCategory.AUTH_REQUIRED: HTTPStatus.UNAUTHORIZED,
    ErrorCategory.PERMISSION: HTTPStatus.FORBIDDEN,
    ErrorCategory.CONFLICT: HTTPStatus.CONFLICT,
    ErrorCategory.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCategory.DEPENDENCY: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCategory.INTERNAL: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCategory.CATALOG_INTEGRITY: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCategory.AUTHORIZATION_PENDING: HTTPStatus.BAD_REQUEST,
    ErrorCategory.AUTHORIZATION_EXPIRED: HTTPStatus.BAD_REQUEST,
    ErrorCategory.AUTHORIZATION_DECLINED: HTTPStatus.BAD_REQUEST,
    ErrorCategory.PRECONDITION: HTTPStatus.PRECONDITION_FAILED,
    ErrorCategory.DEVICE_REVOKED: HTTPStatus.FORBIDDEN,
}

_RETRYABLE: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.DEPENDENCY,
        ErrorCategory.AUTHORIZATION_PENDING,
    }
)

_STATUS_CATEGORY: Mapping[int, ErrorCategory] = {
    HTTPStatus.BAD_REQUEST: ErrorCategory.VALIDATION,
    HTTPStatus.NOT_FOUND: ErrorCategory.NOT_FOUND,
    HTTPStatus.UNAUTHORIZED: ErrorCategory.AUTH_REQUIRED,
    HTTPStatus.FORBIDDEN: ErrorCategory.PERMISSION,
    HTTPStatus.CONFLICT: ErrorCategory.CONFLICT,
    HTTPStatus.PRECONDITION_FAILED: ErrorCategory.PRECONDITION,
    HTTPStatus.TOO_MANY_REQUESTS: ErrorCategory.RATE_LIMITED,
    HTTPStatus.SERVICE_UNAVAILABLE: ErrorCategory.DEPENDENCY,
}


class ApiError(Exception):
    """A domain error carrying a category and a safe client message."""

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        *,
        details: Mapping[str, str] | None = None,
    ) -> None:
        self.category = category
        self.message = message
        self.details = dict(details or {})
        super().__init__(message)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _build(
    request: Request, category: ErrorCategory, message: str, details: Mapping[str, object]
) -> JSONResponse:
    code = CATEGORY_CODE[category]
    # exit_class_for validates the code is registered; its value is owned by
    # the foundation registry and surfaced via docs/contracts/http-api.md.
    exit_class_for(code)
    return error_response(
        request_id=_request_id(request),
        code=code,
        message=message,
        retryable=category in _RETRYABLE,
        status_code=int(CATEGORY_STATUS[category]),
        details=dict(details),
    )


def status_to_category(status_code: int) -> ErrorCategory:
    """Map an HTTP status to the nearest stable API error category."""
    mapped = _STATUS_CATEGORY.get(status_code)
    if mapped is not None:
        return mapped
    return ErrorCategory.INTERNAL if status_code >= 500 else ErrorCategory.VALIDATION


async def _api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, ApiError) else ApiError(ErrorCategory.INTERNAL, "internal error")
    return _build(request, error.category, error.message, error.details)


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    fields: list[str] = []
    if isinstance(exc, RequestValidationError):
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    return _build(
        request, ErrorCategory.VALIDATION, "request validation failed", {"fields": fields}
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    status_code = exc.status_code if isinstance(exc, StarletteHTTPException) else 500
    category = status_to_category(status_code)
    return _build(request, category, HTTPStatus(status_code).phrase, {})


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.error("unhandled_exception", error_type=type(exc).__name__)
    return _build(request, ErrorCategory.INTERNAL, "internal error", {})


def register_exception_handlers(app: FastAPI) -> None:
    """Register the envelope-producing exception handlers on the app."""
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
