"""What a program-lifecycle plan must say before any byte is fetched.

The consumer downloads and the provider never does, so the plan is the only
place the identity of those bytes is stated. Everything here is about refusing a
plan that leaves that identity open.
"""

from __future__ import annotations

from typing import cast

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import operation_v3, protocol_v3
from ai_stp_foundation.canonical import JsonValue

DIGEST = "sha256:" + "b" * 64


def _artifact(**overrides: JsonValue) -> dict[str, JsonValue]:
    complete: dict[str, JsonValue] = {
        "platform": "linux/x86_64",
        "url": "https://registry.example.invalid/opencode-1.18.23.tgz",
        "sha256": DIGEST,
        "byte_length": 60167326,
        "entry_point": "bin/opencode",
    }
    return {**complete, **overrides}


def _plan(*artifacts: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"software_artifacts": cast(list[JsonValue], list(artifacts))}


def test_a_complete_artifact_is_read_exactly() -> None:
    read = operation_v3.require_software_artifacts(
        _plan(_artifact()), operation=protocol_v3.Operation.SOFTWARE_INSTALL
    )

    assert len(read) == 1
    only = read[0]
    assert only.sha256 == DIGEST
    assert only.byte_length == 60167326
    assert only.entry_point == "bin/opencode"
    assert only.platform == "linux/x86_64"


@pytest.mark.parametrize("field", ["platform", "url", "sha256", "byte_length", "entry_point"])
def test_every_field_is_required(field: str) -> None:
    """Four of five is not an identity; without any one of them something is open."""
    partial = _artifact()
    del partial[field]

    with pytest.raises(CliFailure) as raised:
        operation_v3.require_software_artifacts(
            _plan(partial), operation=protocol_v3.Operation.SOFTWARE_INSTALL
        )

    assert field in raised.value.message or field in str(raised.value.details)


def test_an_install_plan_with_no_artifacts_is_refused() -> None:
    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(), operation=protocol_v3.Operation.SOFTWARE_INSTALL
        )


def test_a_digest_that_is_not_one_is_refused() -> None:
    """The digest is the whole trust anchor: the URL is only a hint."""
    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(_artifact(sha256="not-a-digest")),
            operation=protocol_v3.Operation.SOFTWARE_INSTALL,
        )


@pytest.mark.parametrize("length", [0, -1, "60167326"])
def test_a_length_that_cannot_be_checked_is_refused(length: JsonValue) -> None:
    """A length is checked against the bytes; a string or zero checks nothing."""
    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(_artifact(byte_length=length)),
            operation=protocol_v3.Operation.SOFTWARE_INSTALL,
        )


@pytest.mark.parametrize(
    "url", ["http://registry.example.invalid/x.tgz", "file:///etc/passwd", "registry/x.tgz"]
)
def test_only_https_is_fetched(url: str) -> None:
    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(_artifact(url=url)), operation=protocol_v3.Operation.SOFTWARE_INSTALL
        )


@pytest.mark.parametrize("entry", ["/usr/bin/opencode", "../../escape", "bin/../../escape"])
def test_an_entry_point_that_leaves_the_prefix_is_refused(entry: str) -> None:
    """`entry_point` is relative to `--prefix` and stays under it.

    The provider creates it, not us, but it is reported to an agent and joined
    against the prefix by whoever reads it, so a value that escapes is refused
    here rather than trusted downstream.
    """
    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(_artifact(entry_point=entry)),
            operation=protocol_v3.Operation.SOFTWARE_INSTALL,
        )


def test_remove_carries_no_artifacts() -> None:
    """`software_remove` needs no bytes; a plan offering some is not that operation."""
    assert (
        operation_v3.require_software_artifacts({}, operation=protocol_v3.Operation.SOFTWARE_REMOVE)
        == ()
    )

    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(_artifact()), operation=protocol_v3.Operation.SOFTWARE_REMOVE
        )


def test_a_non_software_operation_may_not_carry_artifacts() -> None:
    """Installing a setup is not installing a program, whatever the plan offers."""
    with pytest.raises(CliFailure):
        operation_v3.require_software_artifacts(
            _plan(_artifact()), operation=protocol_v3.Operation.INSTALL
        )
