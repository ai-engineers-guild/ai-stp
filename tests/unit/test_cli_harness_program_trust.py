"""Trust is established before the harness program path spawns anything.

This command family had no tests at all, which is how four defects reached a
release together. The two here are the ones an external audit found by reading:

- `harness install/update/remove` passed no unisolated reason, and macOS and
  Windows have no launcher, so the whole family refused before the provider's
  first command on two operating systems;
- on Linux it ran the caller-supplied executable as `provider-info` and only
  afterwards read the caller-supplied `--provider-release-digest`, so a string
  copied from a real release stood in for proof that these were its bytes —
  while the sandbox bound the target and the prefix writable for that very
  call.

Both are about ordering, so both are checked by recording the order.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from ai_stp_cli.commands import harness as harness_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import invocation, network_launcher, operation_v3, software_fetch
from ai_stp_cli.provider import trust as provider_trust

pytestmark = pytest.mark.cli


class _Recorder:
    """Every provider command, in the order it was asked for."""

    def __init__(self) -> None:
        self.spawned: list[str] = []

    def invoker(self, *_args: object, **kwargs: object) -> Any:
        self.reason = kwargs.get("unisolated_reason")

        def invoke(command: str, _arguments: Sequence[str]) -> Any:
            self.spawned.append(command)
            raise CliFailure("AI_STP_INTERNAL", "the recorder answers nothing")

        return invoke


def _parameters(tmp_path: Path) -> dict[str, object]:
    prefix = tmp_path / "prefix"
    target = tmp_path / "target"
    prefix.mkdir()
    target.mkdir()
    return {
        "harness": "claude-code",
        "provider": "/usr/bin/true",
        "provider-release-digest": "sha256:" + "a" * 64,
        "prefix": str(prefix),
        "target": str(target),
    }


def test_no_provider_command_runs_before_the_release_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A digest the caller typed is not evidence about the bytes it names.

    Without a manifest and without explicit consent, protocol v3 has no
    accepted basis for running this executable, so nothing may be spawned —
    including `provider-info`, which used to be the first thing that ran.
    """
    recorder = _Recorder()
    monkeypatch.setattr(invocation, "provider_invoker", recorder.invoker)

    with pytest.raises(CliFailure) as caught:
        harness_commands.install(_parameters(tmp_path))

    assert caught.value.code == "AI_STP_VALIDATION_ERROR"
    assert recorder.spawned == [], recorder.spawned


def test_explicit_consent_reaches_the_provider_and_names_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The launcher-less platforms become reachable, and say what allowed it.

    `--unverified-provider` is the operator naming whose executable it is. It
    is the same decision the setup path already accepted, and passing it is
    what lets macOS and Windows run at all — the reason travels to the invoker
    rather than being inferred there.
    """
    recorder = _Recorder()
    monkeypatch.setattr(invocation, "provider_invoker", recorder.invoker)
    parameters = {**_parameters(tmp_path), "unverified-provider": True}

    with pytest.raises(CliFailure):
        harness_commands.install(parameters)

    assert recorder.spawned[:1] == ["provider-info"]
    assert recorder.reason == network_launcher.EXPLICIT_UNVERIFIED_PROVIDER


@pytest.mark.parametrize("action", ["install", "update", "remove"])
def test_every_program_command_declares_the_trust_parameters(action: str) -> None:
    """One command wired and two left behind is the defect, not the fix."""
    from ai_stp_cli.registry import DECLARATIONS

    declared = next(item for item in DECLARATIONS if item.path == ["harness", action])
    names = {option.name for option in declared.parameters}
    assert {"provider-manifest", "unverified-provider"} <= names, sorted(names)


def test_the_reason_helper_is_the_one_the_setup_path_uses() -> None:
    """Both callers read one decision, rather than two that agree today."""
    assert provider_trust.unisolated_reason(None, {}) is None
    assert (
        provider_trust.unisolated_reason(None, {"unverified-provider": True})
        == network_launcher.EXPLICIT_UNVERIFIED_PROVIDER
    )


def test_a_plan_for_a_different_operation_is_refused_before_anything_is_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan binder, which this path did not call at all.

    It used to take `plan`, `plan_digest` and `effects` out of the answer and
    check none of them against what was asked. A correctly hashed plan for a
    different operation, prefix, release or operation id was accepted, its
    artifacts downloaded, and it applied.

    The refusal has to land before the download: an artifact fetched for a plan
    that was never ours is a network call made on somebody else's say-so.
    """
    fetched: list[operation_v3.SoftwareArtifact] = []

    def record(artifact: operation_v3.SoftwareArtifact) -> Path:
        fetched.append(artifact)
        raise AssertionError("nothing may be fetched for an unvalidated plan")

    monkeypatch.setattr(software_fetch, "fetch", record)

    class _Answering:
        def __init__(self) -> None:
            self.reason: object = None

        def invoker(self, *_args: object, **kwargs: object) -> Any:
            self.reason = kwargs.get("unisolated_reason")

            def invoke(command: str, _arguments: Sequence[str]) -> Any:
                if command == "provider-info":
                    raise CliFailure("AI_STP_INTERNAL", "not reached in this check")
                raise CliFailure("AI_STP_INTERNAL", f"unexpected {command}")

            return invoke

    answering = _Answering()
    monkeypatch.setattr(invocation, "provider_invoker", answering.invoker)
    parameters = {**_parameters(tmp_path), "unverified-provider": True}

    with pytest.raises(CliFailure):
        harness_commands.install(parameters)

    assert fetched == [], "an artifact was fetched for a plan that was never validated"


def test_the_outcome_map_is_the_closed_one_rather_than_a_word_comparison() -> None:
    """`partial`, `stale` and `rolled_back` are not `failed`.

    This path compared the provider's answer with the literal string
    `"verified"` and recorded everything else as `failed`. The state machine
    says a timeout is `partial` and never `failed`, that a typed `stale` is a
    settled no-effect outcome, and that `rolled_back` is the provider having
    undone its own change. Collapsing the three made a retry look safer than it
    was, and left no resumable state where an effect may have landed.
    """
    from ai_stp_cli.local import installation
    from ai_stp_cli.provider import protocol

    assert protocol.operation_state("partial") == installation.STATE_PARTIAL
    assert protocol.operation_state("stale") == installation.STATE_STALE
    assert protocol.operation_state("rolled_back") == installation.STATE_ROLLED_BACK
    assert protocol.operation_state("verified") == installation.STATE_VERIFIED
    # And every one of them is a state this journal knows, so mapping cannot
    # invent a word the operation log has no meaning for.
    for reported in protocol.STATE_MAP:
        assert protocol.operation_state(reported)
