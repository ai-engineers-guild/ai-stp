"""The machine surface identifies itself, and a version string does not.

Two builds can report the same distribution version with different registries —
a source checkout and a released wheel routinely do — so a caller that kept
`help --agent` "for this version" ends up constructing calls the running build
does not accept. The fingerprint is what makes that detectable, which only works
if it changes exactly when the surface does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from ai_stp_cli.commands import machine_help
from ai_stp_cli.local.database import SCHEMA_VERSION
from ai_stp_cli.registry import COMMANDS, registry_digest
from ai_stp_foundation.digests import is_digest


def test_the_fingerprint_is_a_digest_and_is_stable_across_calls() -> None:
    first = registry_digest()
    assert is_digest(first)
    assert registry_digest() == first


def test_both_introspection_answers_report_the_same_surface() -> None:
    # They read one registry, so they cannot disagree about which build a
    # caller is talking to either.
    assert machine_help.capabilities({}).payload.registry_digest == registry_digest()
    assert machine_help.registry({}).payload.registry_digest == registry_digest()


def test_capabilities_names_the_local_schema_this_build_reads() -> None:
    # Data written by a newer build is refused rather than downgraded. Saying
    # which schema this build speaks lets a caller see that before a command
    # hits it.
    assert machine_help.capabilities({}).payload.local_schema_version == SCHEMA_VERSION


def test_a_changed_command_surface_changes_the_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = registry_digest()
    monkeypatch.setattr("ai_stp_cli.registry.COMMANDS", COMMANDS[:-1])
    assert registry_digest() != before


def test_a_changed_error_disposition_changes_the_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An agent reads `handling` to decide what to do after a failure.

    A build that answers the same code differently is a different surface, even
    with the same commands and the same version.
    """
    from ai_stp_foundation.errors import ERROR_CODES, ErrorCodeEntry

    before = registry_digest()
    entry = ERROR_CODES["AI_STP_CONFLICT"]
    altered: Mapping[str, ErrorCodeEntry] = {
        **ERROR_CODES,
        "AI_STP_CONFLICT": ErrorCodeEntry(entry.exit_class, "ask_user", entry.description),
    }
    monkeypatch.setattr("ai_stp_cli.registry.ERROR_CODES", cast(object, altered))
    assert registry_digest() != before


def test_a_scoped_read_returns_one_family_and_still_names_the_build() -> None:
    """The relevance judgement is what a bounded answer removes.

    An agent that needs one command does not need every descriptor this build
    offers in order to construct it, and reading them all is work it repeats on
    every task.
    """
    whole = machine_help.registry({}).payload
    scoped = machine_help.registry({"path": "project sync"}).payload

    assert [" ".join(command.path) for command in scoped.commands] == [
        "project sync apply",
        "project sync plan",
    ]
    revision = machine_help.registry({"path": "project revision"}).payload
    assert [" ".join(command.path) for command in revision.commands] == [
        "project revision pull",
        "project revision push",
    ]
    assert len(scoped.commands) < len(whole.commands)
    # A scoped read describes the same build as a full one, so what a caller
    # kept from either stays comparable.
    assert scoped.registry_digest == whole.registry_digest
    assert scoped.global_options == whole.global_options
    assert scoped.error_codes == whole.error_codes


def test_an_exact_command_can_be_read_on_its_own() -> None:
    scoped = machine_help.registry({"path": "project sync apply"}).payload
    assert [command.path for command in scoped.commands] == [["project", "sync", "apply"]]


def test_a_path_no_command_lives_under_is_refused_rather_than_answered_empty() -> None:
    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure) as raised:
        machine_help.registry({"path": "not a family"})
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert raised.value.details["path"] == "not a family"


def test_the_whole_registry_is_still_the_default() -> None:
    from ai_stp_cli.registry import descriptors

    assert len(machine_help.registry({}).payload.commands) == len(descriptors())
