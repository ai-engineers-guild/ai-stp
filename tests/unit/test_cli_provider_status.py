"""Provider-observed authorization readiness (`ADR-0052`)."""

import json

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import status
from ai_stp_foundation.canonical import JsonValue


def test_omitted_authorization_evidence_is_compatible_but_not_ready() -> None:
    assert status.authorization({"state": "verified"}) is None


@pytest.mark.parametrize("state", ["pending", "ready"])
def test_authorization_evidence_has_a_closed_state(state: str) -> None:
    found = status.authorization({"authorization": {"kind": "external_service", "state": state}})

    assert found is not None
    assert found.kind == "external_service"
    assert found.ready is (state == "ready")


@pytest.mark.parametrize(
    ("answer", "field"),
    [
        ({"authorization": "ready"}, "authorization"),
        ({"authorization": {"kind": "unknown", "state": "ready"}}, "authorization.kind"),
        (
            {"authorization": {"kind": "user_account", "state": "unknown"}},
            "authorization.state",
        ),
    ],
)
def test_malformed_evidence_fails_closed_without_echoing_values(
    answer: dict[str, JsonValue], field: str
) -> None:
    with pytest.raises(CliFailure) as raised:
        status.authorization(answer)

    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"
    assert raised.value.details == {"field": field}
    assert "unknown" not in raised.value.message
    assert "unknown" not in json.dumps(raised.value.details)
