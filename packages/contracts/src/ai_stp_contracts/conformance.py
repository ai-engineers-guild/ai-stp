"""Replayable `/v1` conformance suite (issue #71).

The suite an implementation must pass, shipped with the contract rather than
written twice. The platform's own tests point it at their ASGI app; this
repository points it at the mock. One suite, so "the mock is conformant" and
"the API is conformant" mean the same thing — and a divergence shows up as a
failing case instead of a live bug.

It is deliberately transport-shaped rather than framework-shaped: it needs an
`httpx.Client`, so it works against a mock transport, an ASGI transport or a
deployed URL without knowing which.

Findings are returned rather than asserted. A caller decides how to report
them, and a suite that raised on the first problem would hide the other
nineteen.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast

import httpx

from ai_stp_contracts.fixtures import FixtureCase, load_cases
from ai_stp_contracts.http import API_BASE_PATH, REQUEST_ID_HEADER
from ai_stp_contracts.openapi import OPERATIONS, Operation

_BY_ID: Final[dict[str, Operation]] = {
    operation.operation_id: operation for operation in OPERATIONS
}


@dataclass(frozen=True)
class Finding:
    """One way an implementation departed from the contract."""

    case_id: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.case_id}: {self.detail}"


def _url(case: FixtureCase, operation: Operation) -> str:
    path = f"{API_BASE_PATH}{operation.path}"
    for name, value in case.request.path_params.items():
        path = path.replace("{" + name + "}", value)
    return path


def _query(case: FixtureCase) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, value in case.request.query.items():
        rendered[name] = "true" if value is True else "false" if value is False else str(value)
    return rendered


def _check_case(client: httpx.Client, case: FixtureCase) -> list[Finding]:
    operation = _BY_ID[case.operation_id]
    try:
        response = client.request(
            operation.method.upper(),
            _url(case, operation),
            params=_query(case),
            json=dict(case.request.body) if case.request.body is not None else None,
            headers=dict(case.request.headers),
        )
    except Exception as error:  # pragma: no cover - only on a broken implementation
        return [Finding(case.case_id, f"request raised {type(error).__name__}: {error}")]

    findings: list[Finding] = []
    if response.status_code != case.status:
        findings.append(
            Finding(case.case_id, f"status {response.status_code}, contract says {case.status}")
        )
    if REQUEST_ID_HEADER not in response.headers:
        findings.append(Finding(case.case_id, f"no {REQUEST_ID_HEADER} header"))

    try:
        payload = cast(object, response.json())
    except json.JSONDecodeError:
        return [*findings, Finding(case.case_id, "body is not JSON")]

    if case.kind == "positive":
        if payload != dict(case.body or {}):
            findings.append(Finding(case.case_id, "body differs from the contract example"))
        return findings

    code: object = None
    if isinstance(payload, dict):
        error = cast(dict[str, object], payload).get("error")
        if isinstance(error, dict):
            code = cast(dict[str, object], error).get("code")
    if code != case.error_code:
        findings.append(
            Finding(case.case_id, f"error code {code!r}, contract says {case.error_code!r}")
        )
    return findings


def run_conformance(
    client: httpx.Client, cases: Sequence[FixtureCase] | None = None
) -> list[Finding]:
    """Replay every replayable case and report every departure.

    Two kinds are skipped. `invalid_response` describes a body a **client** must
    refuse, so replaying it would ask an implementation to be wrong on purpose.
    `example` describes a valid body no request can select, because it depends
    on server state; replaying it would demand a deployment be unhealthy. Both
    are exercised against the models instead.
    """
    corpus = tuple(cases) if cases is not None else load_cases()
    findings: list[Finding] = []
    for case in corpus:
        if case.kind not in {"positive", "rejected_request"}:
            continue
        findings.extend(_check_case(client, case))
    return findings


def replayable_cases(cases: Sequence[FixtureCase] | None = None) -> tuple[FixtureCase, ...]:
    """The cases `run_conformance` will actually send."""
    corpus = tuple(cases) if cases is not None else load_cases()
    return tuple(case for case in corpus if case.kind in {"positive", "rejected_request"})
