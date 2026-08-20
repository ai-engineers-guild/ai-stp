# pyright: reportPrivateUsage=false
"""Unit tests for error-category mapping (SPEC-017 REQ-1706)."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.types import Scope

from ai_stp_api.errors import (
    CATEGORY_CODE,
    CATEGORY_STATUS,
    ApiError,
    ErrorCategory,
    _api_error_handler,
    _http_exception_handler,
    _unhandled_handler,
    _validation_handler,
    status_to_category,
)
from ai_stp_foundation.errors import is_registered_code
from ai_stp_foundation.ids import new_id

pytestmark = pytest.mark.platform


def _request() -> Request:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/v1/x",
        "raw_path": b"/v1/x",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("test", 443),
    }
    request = Request(scope)
    request.state.request_id = new_id("request")
    return request


def test_every_category_maps_to_a_registered_code() -> None:
    for category in ErrorCategory:
        assert is_registered_code(CATEGORY_CODE[category])


def test_every_category_has_a_status() -> None:
    for category in ErrorCategory:
        assert category in CATEGORY_STATUS


def test_unknown_server_status_maps_to_internal() -> None:
    assert status_to_category(500) is ErrorCategory.INTERNAL


def test_unknown_client_status_maps_to_validation() -> None:
    assert status_to_category(418) is ErrorCategory.VALIDATION


def test_not_found_status_maps_to_not_found() -> None:
    assert status_to_category(404) is ErrorCategory.NOT_FOUND


def test_known_status_maps_to_its_category() -> None:
    assert status_to_category(int(HTTPStatus.CONFLICT)) is ErrorCategory.CONFLICT


@pytest.mark.asyncio
async def test_handlers_emit_envelope_without_internal_detail() -> None:
    # Breakage: unhandled or HTTP errors leak stack traces or wrong categories.
    request = _request()

    api = await _api_error_handler(request, ApiError(ErrorCategory.NOT_FOUND, "missing resource"))
    assert api.status_code == int(HTTPStatus.NOT_FOUND)
    body = api.body
    assert b"AI_STP_NOT_FOUND" in body
    assert b"missing resource" in body

    http = await _http_exception_handler(
        request, StarletteHTTPException(status_code=404, detail="gone")
    )
    assert http.status_code == 404
    assert b"AI_STP_NOT_FOUND" in http.body

    # Non-HTTP exception path in the HTTP handler falls back to 500.
    fallback = await _http_exception_handler(request, RuntimeError("boom"))
    assert fallback.status_code == 500
    assert b"AI_STP_INTERNAL" in fallback.body

    unhandled = await _unhandled_handler(request, RuntimeError("secret path"))
    assert unhandled.status_code == 500
    assert b"AI_STP_INTERNAL" in unhandled.body
    assert b"secret path" not in unhandled.body

    validation = await _validation_handler(
        request,
        RequestValidationError(
            [{"type": "missing", "loc": ("body", "name"), "msg": "Field required", "input": {}}]
        ),
    )
    assert validation.status_code == int(HTTPStatus.BAD_REQUEST)
    assert b"AI_STP_VALIDATION_ERROR" in validation.body
    assert b"body.name" in validation.body
