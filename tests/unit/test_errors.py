"""Error-code registry: closed, well-formed, mapped to contract exit classes."""

import re

import pytest

from ai_stp_foundation.errors import (
    ERROR_CODE_PATTERN,
    ERROR_CODES,
    VALID_EXIT_CLASSES,
    error_code_schema,
    exit_class_for,
    is_registered_code,
)

EXPECTED_HANDLING = {
    "AI_STP_VALIDATION_ERROR": "correct_request",
    "AI_STP_UNSUPPORTED_APPLY": "correct_request",
    "AI_STP_NOT_FOUND": "correct_request",
    "AI_STP_SCHEMA_UNSUPPORTED": "correct_request",
    "AI_STP_AUTH_REQUIRED": "authenticate",
    "AI_STP_AUTHORIZATION_PENDING": "await_authorization",
    "AI_STP_AUTHORIZATION_EXPIRED": "restart_authorization",
    "AI_STP_AUTHORIZATION_DECLINED": "restart_authorization",
    "AI_STP_PERMISSION_DENIED": "stop_for_permission",
    "AI_STP_DEVICE_REVOKED": "restart_authorization",
    "AI_STP_CONFLICT": "reconcile_state",
    "AI_STP_PLAN_STALE": "reconcile_state",
    "AI_STP_PRECONDITION_FAILED": "reconcile_state",
    "AI_STP_USER_DECISION_REQUIRED": "ask_user",
    "AI_STP_RATE_LIMITED": "retry_if_retryable",
    "AI_STP_DEPENDENCY_UNAVAILABLE": "retry_if_retryable",
    "AI_STP_TIMEOUT_UNCONFIRMED": "inspect_effect",
    "AI_STP_PARTIAL_OPERATION": "recover_partial",
    "AI_STP_CATALOG_INTEGRITY": "report_bug",
    "AI_STP_INTERNAL": "report_bug",
}


def test_every_code_is_well_formed_and_mapped() -> None:
    pattern = re.compile(ERROR_CODE_PATTERN)
    for code, entry in ERROR_CODES.items():
        assert pattern.fullmatch(code), code
        assert entry.exit_class in VALID_EXIT_CLASSES, code
        assert entry.handling == EXPECTED_HANDLING[code]
        assert entry.description
    assert set(EXPECTED_HANDLING) == set(ERROR_CODES)


def test_documented_codes_are_registered() -> None:
    assert is_registered_code("AI_STP_VALIDATION_ERROR")
    assert is_registered_code("AI_STP_UNSUPPORTED_APPLY")
    assert exit_class_for("AI_STP_UNSUPPORTED_APPLY") == 2


def test_registry_is_immutable_and_unique() -> None:
    with pytest.raises(TypeError):
        ERROR_CODES["AI_STP_HACK"] = ERROR_CODES["AI_STP_INTERNAL"]  # type: ignore[index]
    assert len(set(ERROR_CODES)) == len(ERROR_CODES)


def test_unregistered_code_fails_closed() -> None:
    assert not is_registered_code("AI_STP_UNKNOWN_THING")
    with pytest.raises(KeyError):
        exit_class_for("AI_STP_UNKNOWN_THING")


def test_schema_enum_is_sorted_and_complete() -> None:
    schema = error_code_schema()
    assert schema["enum"] == sorted(ERROR_CODES)
    assert schema["type"] == "string"
