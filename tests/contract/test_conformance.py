"""The mock is conformant, and the suite that proves it is the one the platform runs.

If the mock had its own opinion about the contract, the CLI could pass against
behaviour the platform never has to provide. Running the shipped conformance
suite against the mock closes that: "the mock is conformant" and "the API is
conformant" are then the same statement, checked the same way.
"""

import httpx
import pytest

from ai_stp_contracts.conformance import Finding, replayable_cases, run_conformance
from ai_stp_contracts.fixtures import case, cases_of_kind, load_cases
from ai_stp_contracts.http import REQUEST_ID_HEADER
from ai_stp_contracts.mock import (
    MOCK_BASE_URL,
    UnmatchedRequest,
    build_client,
    build_transport,
)


def test_the_mock_passes_the_shipped_conformance_suite() -> None:
    with build_client() as client:
        findings = run_conformance(client)
    assert findings == [], "\n".join(str(finding) for finding in findings)


def test_the_suite_replays_every_case_that_can_be_replayed() -> None:
    # An `invalid_response` case describes a body a client must refuse, so
    # replaying it would ask an implementation to be wrong on purpose.
    replayable = {item.case_id for item in replayable_cases()}
    expected = {
        item.case_id for item in load_cases() if item.kind in {"positive", "rejected_request"}
    }
    assert replayable == expected
    assert replayable, "the corpus must have something to replay"


def test_the_suite_reports_rather_than_raises() -> None:
    # A suite that stopped on the first problem would hide the rest, which is
    # exactly what an implementer needs to see.
    def wrong(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"unexpected": True})

    with httpx.Client(transport=httpx.MockTransport(wrong), base_url=MOCK_BASE_URL) as client:
        findings = run_conformance(client)
    assert len(findings) > 1
    assert all(isinstance(finding, Finding) for finding in findings)


def test_a_wrong_status_is_reported_with_both_numbers() -> None:
    def wrong_status(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={}, headers={REQUEST_ID_HEADER: "request_x"})

    with httpx.Client(transport=httpx.MockTransport(wrong_status), base_url=MOCK_BASE_URL) as c:
        findings = run_conformance(c, [case("healthLive.answering")])
    assert any("418" in finding.detail and "200" in finding.detail for finding in findings)


def test_a_missing_correlation_header_is_reported() -> None:
    def headerless(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=dict(case("healthLive.answering").body or {}))

    with httpx.Client(transport=httpx.MockTransport(headerless), base_url=MOCK_BASE_URL) as c:
        findings = run_conformance(c, [case("healthLive.answering")])
    assert any(REQUEST_ID_HEADER in finding.detail for finding in findings)


def test_a_wrong_error_code_is_reported() -> None:
    # Two implementations failing differently must not both look correct.
    def wrong_code(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"code": "AI_STP_INTERNAL"}},
            headers={REQUEST_ID_HEADER: "request_x"},
        )

    target = case("searchComponents.unknownFilter")
    with httpx.Client(transport=httpx.MockTransport(wrong_code), base_url=MOCK_BASE_URL) as c:
        findings = run_conformance(c, [target])
    assert any("AI_STP_VALIDATION_ERROR" in finding.detail for finding in findings)


def test_a_non_json_body_is_reported() -> None:
    def not_json(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>", headers={REQUEST_ID_HEADER: "request_x"})

    with httpx.Client(transport=httpx.MockTransport(not_json), base_url=MOCK_BASE_URL) as c:
        findings = run_conformance(c, [case("healthLive.answering")])
    assert any("not JSON" in finding.detail for finding in findings)


def test_the_mock_refuses_an_unforeseen_request() -> None:
    # A mock that invented an answer would teach the client behaviour nobody
    # agreed to, and the CLI would then depend on it.
    # This identifier is well formed and appears in no case, unlike the one the
    # corpus uses for its not-found rejection.
    with build_client() as client, pytest.raises(UnmatchedRequest):
        client.get("/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y71")


def test_the_mock_refuses_an_unknown_route() -> None:
    with build_client() as client, pytest.raises(UnmatchedRequest):
        client.get("/v1/does-not-exist")


def test_the_mock_serves_only_what_a_request_can_select() -> None:
    # `invalid_response` bodies exist to be rejected by the models, and an
    # `example` body depends on server state rather than the call. Serving
    # either would make the mock ambiguous or wrong on purpose.
    transport = build_transport()
    with httpx.Client(transport=transport, base_url=MOCK_BASE_URL) as client:
        response = client.get("/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert cases_of_kind("invalid_response"), "the corpus must carry client-side negatives"
    assert cases_of_kind("example"), "the corpus must carry state-dependent bodies"


def test_the_mock_answers_deterministically() -> None:
    with build_client() as client:
        first = client.get("/v1/health/live")
        second = client.get("/v1/health/live")
    assert first.json() == second.json()
    assert first.headers[REQUEST_ID_HEADER] == second.headers[REQUEST_ID_HEADER]


def test_consent_selects_the_experimental_lane() -> None:
    # The same route with and without consent is two corpus cases, and the mock
    # must tell them apart by the request rather than by order.
    with build_client() as client:
        without = client.get(
            "/v1/catalog/components",
            params={"q": "pytest", "page_size": "20", "include_experimental": "false"},
        )
        with_consent = client.get(
            "/v1/catalog/components",
            params={"q": "pytest", "page_size": "20", "include_experimental": "true"},
        )
    assert without.json()["experimental"] == []
    assert len(with_consent.json()["experimental"]) == 1


def test_a_body_where_the_corpus_expects_none_does_not_match() -> None:
    # `_matches` must distinguish a bodiless call from one carrying a body:
    # otherwise a POST with junk would be answered as if it were the GET case.
    with build_client() as client, pytest.raises(UnmatchedRequest):
        client.request("GET", "/v1/health/live", json={"unexpected": True})


def test_a_missing_body_where_the_corpus_expects_one_does_not_match() -> None:
    # The mirror of the case above: a POST whose corpus case carries a body
    # must not be answered when the caller sent none.
    with build_client() as client, pytest.raises(UnmatchedRequest):
        client.post("/v1/auth/device")
