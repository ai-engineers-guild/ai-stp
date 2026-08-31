"""Protocol-v3 invocation validates status before any caller can read it."""

import os
import stat
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import invocation_v3, protocol_v2
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
