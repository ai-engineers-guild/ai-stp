"""Stable machine error codes (docs/contracts/cli-json.md, issue #63).

A closed immutable registry: every code maps to its exit class from the
cli-json contract and a short description. Producers must emit registered
codes; consumers stay pattern-tolerant so a newer producer's additive code
never breaks an older reader. The registry also exports as a JSON Schema
enum for non-Python consumers.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal, NamedTuple

ERROR_CODE_PATTERN: Final[str] = r"^AI_STP_[A-Z0-9]+(_[A-Z0-9]+)*$"

type ExitClass = Literal[2, 3, 4, 5, 6, 70]

# Exit classes per docs/contracts/cli-json.md.
EXIT_INVALID_INPUT: Final[ExitClass] = 2
EXIT_AUTH: Final[ExitClass] = 3
EXIT_CONFLICT_OR_DECISION: Final[ExitClass] = 4
EXIT_UNAVAILABLE: Final[ExitClass] = 5
EXIT_PARTIAL: Final[ExitClass] = 6
EXIT_INTERNAL: Final[ExitClass] = 70

VALID_EXIT_CLASSES: Final[frozenset[ExitClass]] = frozenset(
    {
        EXIT_INVALID_INPUT,
        EXIT_AUTH,
        EXIT_CONFLICT_OR_DECISION,
        EXIT_UNAVAILABLE,
        EXIT_PARTIAL,
        EXIT_INTERNAL,
    }
)

type ErrorHandling = Literal[
    "correct_request",
    "authenticate",
    "await_authorization",
    "restart_authorization",
    "stop_for_permission",
    "reconcile_state",
    "ask_user",
    "retry_if_retryable",
    "inspect_effect",
    "recover_partial",
    "report_bug",
]


class ErrorCodeEntry(NamedTuple):
    """One registry row: exit class, agent disposition and description."""

    exit_class: ExitClass
    handling: ErrorHandling
    description: str


ERROR_CODES: Final[Mapping[str, ErrorCodeEntry]] = MappingProxyType(
    {
        "AI_STP_VALIDATION_ERROR": ErrorCodeEntry(
            EXIT_INVALID_INPUT, "correct_request", "input or schema validation failed"
        ),
        "AI_STP_UNSUPPORTED_APPLY": ErrorCodeEntry(
            EXIT_INVALID_INPUT,
            "correct_request",
            "apply requested for an unsupported harness",
        ),
        "AI_STP_NOT_FOUND": ErrorCodeEntry(
            EXIT_INVALID_INPUT,
            "correct_request",
            "referenced object or version does not exist",
        ),
        "AI_STP_SCHEMA_UNSUPPORTED": ErrorCodeEntry(
            EXIT_INVALID_INPUT,
            "correct_request",
            "the requested schema or API major version is not supported",
        ),
        "AI_STP_AUTH_REQUIRED": ErrorCodeEntry(
            EXIT_AUTH, "authenticate", "the operation needs a signed-in account"
        ),
        "AI_STP_AUTHORIZATION_PENDING": ErrorCodeEntry(
            EXIT_AUTH,
            "await_authorization",
            "the device authorization is not approved yet",
        ),
        "AI_STP_AUTHORIZATION_EXPIRED": ErrorCodeEntry(
            EXIT_AUTH,
            "restart_authorization",
            "the device authorization request expired before approval",
        ),
        "AI_STP_AUTHORIZATION_DECLINED": ErrorCodeEntry(
            EXIT_AUTH,
            "restart_authorization",
            "the user declined the device authorization",
        ),
        "AI_STP_PERMISSION_DENIED": ErrorCodeEntry(
            EXIT_AUTH,
            "stop_for_permission",
            "the account lacks the required grant or role",
        ),
        "AI_STP_DEVICE_REVOKED": ErrorCodeEntry(
            EXIT_AUTH,
            "restart_authorization",
            "the device key is revoked for cloud operations",
        ),
        "AI_STP_CONFLICT": ErrorCodeEntry(
            EXIT_CONFLICT_OR_DECISION,
            "reconcile_state",
            "concurrent change or revision mismatch",
        ),
        "AI_STP_PLAN_STALE": ErrorCodeEntry(
            EXIT_CONFLICT_OR_DECISION,
            "reconcile_state",
            "the immutable plan no longer matches its preconditions",
        ),
        "AI_STP_PRECONDITION_FAILED": ErrorCodeEntry(
            EXIT_CONFLICT_OR_DECISION,
            "reconcile_state",
            "the supplied revision or ETag no longer matches the object",
        ),
        "AI_STP_USER_DECISION_REQUIRED": ErrorCodeEntry(
            EXIT_CONFLICT_OR_DECISION,
            "ask_user",
            "a sensitive action needs an explicit user decision",
        ),
        "AI_STP_RATE_LIMITED": ErrorCodeEntry(
            EXIT_UNAVAILABLE, "retry_if_retryable", "the server asked to slow down"
        ),
        "AI_STP_DEPENDENCY_UNAVAILABLE": ErrorCodeEntry(
            EXIT_UNAVAILABLE,
            "retry_if_retryable",
            "a required service or resource is unreachable",
        ),
        "AI_STP_TIMEOUT_UNCONFIRMED": ErrorCodeEntry(
            EXIT_UNAVAILABLE,
            "inspect_effect",
            "the call timed out without a confirmed effect",
        ),
        "AI_STP_PARTIAL_OPERATION": ErrorCodeEntry(
            EXIT_PARTIAL,
            "recover_partial",
            "a mutating operation stopped in a partial state",
        ),
        # Distinct from AI_STP_INTERNAL on purpose. A stored catalog object that
        # fails its own integrity check is not an unexpected crash: it is a
        # diagnosable data defect with a known repair path, and an operator has
        # to be able to alert on it without alerting on every unhandled bug.
        # Answering it as AI_STP_NOT_FOUND — the behaviour this code replaces —
        # told the caller the object does not exist while it demonstrably does,
        # which is how a poisoned immutable version hid behind an ordinary miss.
        "AI_STP_CATALOG_INTEGRITY": ErrorCodeEntry(
            EXIT_INTERNAL,
            "report_bug",
            "a stored catalog object failed integrity verification",
        ),
        "AI_STP_INTERNAL": ErrorCodeEntry(EXIT_INTERNAL, "report_bug", "unexpected internal error"),
    }
)


def is_registered_code(code: str) -> bool:
    """Report whether ``code`` is in the closed registry."""
    return code in ERROR_CODES


def exit_class_for(code: str) -> ExitClass:
    """Return the contract exit class of a registered code."""
    entry = ERROR_CODES.get(code)
    if entry is None:
        raise KeyError(f"unregistered error code: {code}")
    return entry.exit_class


def error_code_schema() -> dict[str, object]:
    """Render the registry as a JSON Schema enum for non-Python consumers."""
    return {
        "title": "ErrorCode",
        "description": "Closed registry of stable ai_stp machine error codes.",
        "type": "string",
        "enum": sorted(ERROR_CODES),
    }
