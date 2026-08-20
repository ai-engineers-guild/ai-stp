"""Deterministic `/v1` mock built from the shared corpus (issue #71).

The CLI must be testable before the platform exists, and the mock it tests
against must not be a second opinion about the contract. So this transport
serves the corpus and nothing else: every answer it gives is a case another
implementation is also held to. A mock with its own hand-written responses would
let the CLI pass against behaviour the platform never has to provide.

`httpx` is an optional dependency of this package (`ai-stp-contracts[mock]`).
The platform track imports the corpus and the conformance suite without pulling
an HTTP client it does not need; only a client-side test does.
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Final, cast

import httpx

from ai_stp_contracts.fixtures import FixtureCase, load_cases
from ai_stp_contracts.http import API_BASE_PATH, REQUEST_ID_HEADER
from ai_stp_contracts.openapi import OPERATIONS, Operation

#: A mock answers deterministically, so its correlation id is fixed. A random
#: one would make two runs of the same test differ for no reason.
MOCK_REQUEST_ID: Final[str] = "request_01JQZK7B8N4M6P2R9T5V0X3Y7Z"

MOCK_BASE_URL: Final[str] = "https://mock.ai-stp.invalid"


class UnmatchedRequest(LookupError):
    """No corpus case describes this request.

    Raised rather than answered with a 404: a mock that invents an answer for an
    unforeseen request teaches the client behaviour nobody agreed to.
    """


def _path_regex(operation: Operation) -> re.Pattern[str]:
    pattern = re.escape(f"{API_BASE_PATH}{operation.path}")
    for parameter in operation.path_params:
        pattern = pattern.replace(
            re.escape("{" + parameter.name + "}"), f"(?P<{parameter.name}>[^/]+)"
        )
    return re.compile(f"^{pattern}$")


_ROUTES: Final[tuple[tuple[re.Pattern[str], Operation], ...]] = tuple(
    (_path_regex(operation), operation) for operation in OPERATIONS
)


def _resolve(method: str, path: str) -> tuple[Operation, Mapping[str, str]]:
    for pattern, operation in _ROUTES:
        if operation.method.upper() != method.upper():
            continue
        match = pattern.match(path)
        if match is not None:
            return operation, match.groupdict()
    raise UnmatchedRequest(f"no route for {method} {path}")


def _as_wire(value: object) -> str:
    """Render a fixture value the way it would travel as a query parameter."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _matches(case: FixtureCase, path_params: Mapping[str, str], request: httpx.Request) -> bool:
    if dict(case.request.path_params) != dict(path_params):
        return False
    # Headers select too: a precondition lives in `If-Match`, so two revoke
    # cases can share a path and a body and still be different calls. Matching
    # only path, query and body would make the mock answer whichever sorted
    # first and hide a real distinction.
    for name, expected in case.request.headers.items():
        if request.headers.get(name) != expected:
            return False
    expected_query = {name: _as_wire(value) for name, value in case.request.query.items()}
    if dict(request.url.params) != expected_query:
        return False
    if case.request.body is None:
        return not request.content
    if not request.content:
        return False
    sent = cast(dict[str, object], json.loads(request.content))
    expected = dict(case.request.body)
    # An idempotency key is chosen by the client and opaque to the server, so a
    # fixture pinning its value would be matching on noise. Its presence is
    # guaranteed by the request model, which requires it.
    sent.pop("idempotency_key", None)
    expected.pop("idempotency_key", None)
    return sent == expected


def _error_body(case: FixtureCase) -> dict[str, object]:
    assert case.error_code is not None
    return {
        "schema_version": 1,
        "ok": False,
        "request_id": MOCK_REQUEST_ID,
        "operation_id": None,
        "error": {
            "code": case.error_code,
            "message": case.case_id,
            "retryable": case.error_code == "AI_STP_AUTHORIZATION_PENDING",
            "details": {},
        },
        "next_actions": [],
    }


def build_transport(cases: Sequence[FixtureCase] | None = None) -> httpx.MockTransport:
    """A transport that answers exactly the corpus and refuses everything else."""
    corpus = tuple(cases) if cases is not None else load_cases()
    servable = tuple(case for case in corpus if case.kind in {"positive", "rejected_request"})

    def handle(request: httpx.Request) -> httpx.Response:
        operation, path_params = _resolve(request.method, request.url.path)
        for case in servable:
            if case.operation_id != operation.operation_id:
                continue
            if not _matches(case, path_params, request):
                continue
            body = case.body if case.kind == "positive" else _error_body(case)
            return httpx.Response(
                status_code=case.status,
                json=body,
                headers={REQUEST_ID_HEADER: MOCK_REQUEST_ID},
            )
        raise UnmatchedRequest(f"no corpus case for {request.method} {request.url}")

    return httpx.MockTransport(handle)


def build_client(cases: Sequence[FixtureCase] | None = None) -> httpx.Client:
    """A client bound to the mock transport, for a CLI test that needs no server.

    The base URL is `.invalid` on purpose (RFC 2606): if the transport is ever
    dropped by accident the request fails to resolve instead of reaching a real
    host.
    """
    return httpx.Client(transport=build_transport(cases), base_url=MOCK_BASE_URL)
