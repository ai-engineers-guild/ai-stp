"""Unit tests for HTTP success/error envelope helpers (SPEC-017 REQ-1704)."""

from __future__ import annotations

import json

import pytest

from ai_stp_api.envelope import error_response, success_response
from ai_stp_foundation.errors import is_registered_code
from ai_stp_foundation.ids import new_id

pytestmark = pytest.mark.platform


def test_success_response_wraps_payload_and_optional_fields() -> None:
    request_id = new_id("request")
    operation_id = new_id("operation")
    response = success_response(
        request_id=request_id,
        data={"ok": True},
        operation_id=operation_id,
        warnings=["soft"],
        next_actions=["retry"],
        status_code=201,
    )
    assert response.status_code == 201
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["ok"] is True
    assert payload["request_id"] == request_id
    assert payload["operation_id"] == operation_id
    assert payload["data"] == {"ok": True}
    assert payload["warnings"] == ["soft"]
    assert payload["next_actions"] == ["retry"]


def test_success_response_defaults_empty_collections() -> None:
    request_id = new_id("request")
    response = success_response(request_id=request_id)
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["data"] == {}
    assert payload["warnings"] == []
    assert payload["next_actions"] == []
    assert payload["operation_id"] is None


def test_error_response_uses_registered_code_and_details() -> None:
    request_id = new_id("request")
    code = "AI_STP_VALIDATION_ERROR"
    assert is_registered_code(code)
    response = error_response(
        request_id=request_id,
        code=code,
        message="invalid",
        retryable=False,
        status_code=400,
        details={"fields": ["name"]},
        next_actions=["fix"],
    )
    assert response.status_code == 400
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["ok"] is False
    assert payload["error"]["code"] == code
    assert payload["error"]["message"] == "invalid"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["details"] == {"fields": ["name"]}
    assert payload["next_actions"] == ["fix"]
