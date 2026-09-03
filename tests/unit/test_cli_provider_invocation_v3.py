"""Protocol-v3 invocation validates status before any caller can read it."""

import os
import stat
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import invocation_v3, network_launcher, protocol_v2
from ai_stp_foundation.canonical import JsonValue


class _Launcher:
    def __init__(self, answer: JsonValue) -> None:
        self.answer = answer
        self.capability = protocol_v2.NetworkCapability(
            enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
            os_name="linux",
            launcher_id="test:network-denied",
            evidence=("test",),
        )

    def run(
        self,
        argv: tuple[str, ...],
        *,
        target: Path,
        writable: tuple[Path, ...] = (),
        command: str,
    ) -> JsonValue:
        del argv, target, writable, command
        return self.answer


def _provider(tmp_path: Path) -> Path:
    executable = tmp_path / ("provider.exe" if os.name == "nt" else "provider")
    executable.write_text("provider", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def test_malformed_status_is_refused_at_the_invocation_boundary(tmp_path: Path) -> None:
    launcher = _Launcher({"state": "managed"})

    with pytest.raises(CliFailure) as raised:
        invocation_v3.invoke(
            str(_provider(tmp_path)),
            str(tmp_path),
            "status",
            launcher=launcher,
            capability=launcher.capability,
        )

    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"


def test_non_status_answer_is_not_misclassified_as_status(tmp_path: Path) -> None:
    answer: JsonValue = {"protocol_version": 3}
    launcher = _Launcher(answer)

    observed = invocation_v3.invoke(
        str(_provider(tmp_path)),
        str(tmp_path),
        "provider-info",
        launcher=launcher,
        capability=launcher.capability,
    )

    assert observed == answer


def test_a_container_refusal_is_answered_not_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider cannot leave its isolation by describing an error.

    A retry that ran unisolated when the launcher's answer said "cannot be
    canonicalized" or "Access is denied" was added on 2026-09-02, while
    `0.0.56` could not canonicalize a path inside an AppContainer. The estate
    fixed that in `0.0.57`, so the defect is gone; what the retry left was
    worse than the bug. `detail` is text the provider writes, so any provider
    could step outside the container by choosing one of two phrases, and the
    evidence would not show it: `provider network` is asked once about the
    machine, and the configuration slice records that one answer beside every
    row, so the artifact would still name the AppContainer for a run that
    never entered it.

    The refusal is returned to the caller as the launcher gave it. An
    unisolated phase remains possible and remains decided before the call.
    """
    refusal: JsonValue = {
        "rejected": True,
        "reason": "provider_unavailable",
        "detail": "the target cannot be canonicalized: Access is denied",
    }
    launcher = _Launcher(refusal)
    escapes: list[tuple[str, ...]] = []

    def _record(argv: tuple[str, ...], *, command: str) -> JsonValue:
        del command
        escapes.append(argv)
        return {"rejected": False}

    monkeypatch.setattr("ai_stp_cli.provider.conformance.invoke_argv", _record)
    # The conditions the withdrawn retry needed, all of them. Without these the
    # test passes against the code that had the retry, which is how a guard
    # ends up proving nothing: `excepted` is false on Linux and false without a
    # permission, so the branch was never reached at all.
    monkeypatch.setattr("ai_stp_cli.provider.invocation_v3.platform.system", lambda: "Windows")
    permission = network_launcher.unisolated_local_phase(network_launcher.TRUSTED_RELEASE)

    answer = invocation_v3.invoke(
        str(_provider(tmp_path)),
        str(tmp_path),
        "validate-bundle",
        launcher=launcher,
        capability=launcher.capability,
        unisolated=permission,
    )

    assert answer == refusal
    assert escapes == [], "the provider was re-run outside its launcher"
