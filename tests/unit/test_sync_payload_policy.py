"""One owner for what a private sync payload may carry, and two enforcers of it.

The policy used to exist twice — once in the CLI, once in the server slice —
as byte-identical fragment lists. Only the client grew the `required_env`
carve-out, so a complete canonical passport passed the half that was optional
and was refused by the half that decides. These tests hold the single owner to
the shape real passports actually have, rather than to an invented one.
"""

from typing import cast

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import sync_state
from ai_stp_contracts.first_party import versions
from ai_stp_contracts.sync_payload import (
    MAX_REQUIRED_ENV_ENTRIES,
    SyncPayloadRejection,
    check_sync_payload,
)


def _document(**fields: object) -> dict[str, object]:
    return {"schema_version": 1, "kind": "component", **fields}


def test_every_first_party_passport_crosses_the_sync_boundary() -> None:
    # The oracle is the real launch corpus, not a hand-written sample: a policy
    # that refuses the objects the product ships is refusing the product.
    corpus = versions()
    assert corpus, "the first-party corpus must not be empty for this to prove anything"
    for item in corpus:
        check_sync_payload(item.passport.model_dump(mode="json"))


def test_a_declared_environment_variable_is_carried_and_a_value_is_not() -> None:
    check_sync_payload(
        _document(required_env=[{"name": "GITHUB_TOKEN", "purpose": "read the repository"}])
    )

    with pytest.raises(SyncPayloadRejection) as valued:
        check_sync_payload(
            _document(
                required_env=[
                    {"name": "GITHUB_TOKEN", "purpose": "read the repository", "value": "ghp_x"}
                ]
            )
        )
    # The refusal names where, never what: the value is exactly what must not
    # travel, and an error message travels too.
    assert valued.value.path == "required_env[0]"
    assert "ghp_x" not in str(valued.value)


def test_a_declared_authorization_class_is_carried_and_free_text_is_not() -> None:
    # `requires_authorization` collides with the fragment `authorization` and is
    # a closed three-value enum. Before it was admitted by shape, this single
    # field rejected every object in the launch corpus.
    for declared in ("none", "user_account", "external_service"):
        check_sync_payload(_document(requires_authorization=declared))

    for invented in ("Bearer abc", "", None, {"scheme": "bearer"}):
        with pytest.raises(SyncPayloadRejection) as refused:
            check_sync_payload(_document(requires_authorization=invented))
        assert refused.value.path == "requires_authorization"


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        (_document(required_env={"name": "A", "purpose": "b"}), "required_env"),
        (_document(required_env=["GITHUB_TOKEN"]), "required_env[0]"),
        (_document(required_env=[{"name": "A"}]), "required_env[0]"),
        (_document(required_env=[{"name": "A", "purpose": 7}]), "required_env[0]"),
        (
            _document(
                required_env=[
                    {"name": f"VAR_{index}", "purpose": "p"}
                    for index in range(MAX_REQUIRED_ENV_ENTRIES + 1)
                ]
            ),
            "required_env",
        ),
    ],
)
def test_a_malformed_requirement_fails_closed(payload: dict[str, object], path: str) -> None:
    with pytest.raises(SyncPayloadRejection) as refused:
        check_sync_payload(payload)
    assert refused.value.path == path


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        (_document(access_token="ghp_secret"), "access_token"),
        (_document(facts={"github_token": "ghp_secret"}), "facts.github_token"),
        (_document(device_passport={}), "device_passport"),
        (_document(project_index={}), "project_index"),
        (_document(artifact_bytes="AA=="), "artifact_bytes"),
        (_document(notes=["/home/alice/private"]), "notes[0]"),
        (_document(entry_points=[{"path": "C:\\Users\\alice"}]), "entry_points[0].path"),
        (_document(blob=b"\x00\x01"), "blob"),
    ],
)
def test_what_must_not_travel_is_refused_by_path(payload: dict[str, object], path: str) -> None:
    with pytest.raises(SyncPayloadRejection) as refused:
        check_sync_payload(payload)
    assert refused.value.path == path


def test_a_key_that_is_not_text_is_refused_before_it_can_be_matched() -> None:
    # A non-string key cannot be lowercased or matched against a fragment, so it
    # would slip past every rule below it. It is refused at the root path,
    # because naming a field requires a name.
    with pytest.raises(SyncPayloadRejection) as refused:
        check_sync_payload({1: "value"})
    assert refused.value.path == "/"


def test_the_cli_enforces_the_shared_policy_and_reports_the_field() -> None:
    # The CLI keeps no second copy of the rule; it only turns the shared refusal
    # into its own typed failure, with the field path a caller can act on.
    with pytest.raises(CliFailure) as refused:
        sync_state._validate_payload(  # pyright: ignore[reportPrivateUsage]
            _document(facts={"api_key_value": "x"})
        )
    assert refused.value.code == "AI_STP_VALIDATION_ERROR"
    assert cast(dict[str, object], refused.value.details)["field"] == "facts.api_key_value"
    assert "x" not in str(refused.value.details["field"])
