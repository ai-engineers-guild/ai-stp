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


# --- backups[]: held / hold_reason (provider protocol v3, provider 0.0.7) ---


def test_backups_absent_is_an_older_provider_and_not_an_empty_pool() -> None:
    """Absence means the provider predates the field, not that it holds nothing.

    The distinction is the whole point of reading it. A consumer that maps
    absence to "no copies" reports an unprotected baseline as checked-and-empty
    against every release before `0.0.7`, which is the exact failure the field
    exists to prevent, one version out of date.
    """
    assert status.backups({}) is None
    assert status.backups({"backups": []}) == ()


def test_a_held_copy_carries_the_provider_word_and_the_operator_text() -> None:
    observed = status.backups(
        {
            "backups": [
                {
                    "backup_ref": "slot-000000000001",
                    "held": True,
                    "hold_reason": "baseline for the migration",
                }
            ]
        }
    )
    assert observed is not None
    (only,) = observed
    assert only.backup_ref == "slot-000000000001"
    assert only.held is True
    assert only.hold_reason == "baseline for the migration"
    assert only.reason_recorded is True


def test_the_default_hold_reason_is_a_placeholder_and_not_something_a_person_wrote() -> None:
    """`--reason` is optional and the provider stores a fixed string when it is omitted.

    Measured against the built provider: a hold placed with no reason publishes
    `"no reason recorded"`, and so does a hold placed before reasons existed at
    all. It is displayable text and it is not an answer, so counting it as one
    would report a considered hold where nobody considered anything.
    """
    observed = status.backups(
        {"backups": [{"backup_ref": "slot-1", "held": True, "hold_reason": "no reason recorded"}]}
    )
    assert observed is not None
    assert observed[0].hold_reason == "no reason recorded"
    assert observed[0].reason_recorded is False


def test_an_unheld_copy_reports_a_null_reason_rather_than_an_empty_one() -> None:
    observed = status.backups(
        {"backups": [{"backup_ref": "slot-2", "held": False, "hold_reason": None}]}
    )
    assert observed is not None
    assert observed[0].held is False
    assert observed[0].hold_reason is None
    assert observed[0].reason_recorded is False


def test_a_copy_without_the_field_is_unknown_rather_than_unheld() -> None:
    """Per-element mirror of the rule above, for a provider mid-upgrade."""
    observed = status.backups({"backups": [{"backup_ref": "slot-3"}]})
    assert observed is not None
    assert observed[0].held is None
    assert observed[0].reason_recorded is False


@pytest.mark.parametrize(
    "payload",
    [
        {"backups": {}},
        {"backups": ["slot-1"]},
        {"backups": [{"backup_ref": ""}]},
        {"backups": [{"backup_ref": "slot-1", "held": "true"}]},
        {"backups": [{"backup_ref": "slot-1", "held": True, "hold_reason": 7}]},
    ],
)
def test_a_malformed_backup_list_is_refused_rather_than_read_past(
    payload: dict[str, object],
) -> None:
    with pytest.raises(CliFailure) as caught:
        status.backups(payload)  # pyright: ignore[reportArgumentType]
    assert caught.value.code == "AI_STP_SCHEMA_UNSUPPORTED"
