"""Protocol v2 applies its phase decision to the process it actually starts."""

from __future__ import annotations

import platform
import shutil
import socket
import stat
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.provider import invocation_v2, invocation_v3, network_launcher, protocol_v2
from ai_stp_foundation.canonical import JsonValue


class RecordingLauncher:
    """Unit-test launcher; the real Bubblewrap test below proves enforcement."""

    def __init__(self, capability: protocol_v2.NetworkCapability) -> None:
        self.capability = capability
        self.calls: list[tuple[str, ...]] = []

    def wrap(self, argv: tuple[str, ...], *, target: Path) -> tuple[str, ...]:
        assert target.is_absolute()
        self.calls.append(argv)
        return argv


def _provider(tmp_path: Path, body: str) -> str:
    executable = tmp_path / "provider"
    executable.write_text(f"#!/usr/bin/env python3\n{body}", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return str(executable.resolve())


def _enforced() -> protocol_v2.NetworkCapability:
    return protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="linux",
        launcher_id="test-launcher/1",
        evidence=("test launcher observed network denial",),
    )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return cast(dict[str, JsonValue], value)


def test_local_phase_without_matching_launcher_fails_before_spawn(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    executable = _provider(tmp_path, f"open({str(marker)!r}, 'w').write('yes')\n")

    with pytest.raises(protocol_v2.NetworkCapabilityUnavailable):
        invocation_v2.invoke(
            executable,
            str(tmp_path.resolve()),
            "status",
            protocol_v2.ActionPhase.EXECUTE,
            launcher=None,
            capability=_enforced(),
        )

    assert not marker.exists()


def test_download_is_unwrapped_but_apply_uses_the_proved_launcher(tmp_path: Path) -> None:
    executable = _provider(
        tmp_path,
        "import json, sys\nprint(json.dumps({'argv': sys.argv[1:]}))\n",
    )
    capability = _enforced()
    launcher = RecordingLauncher(capability)

    downloaded = invocation_v2.invoke(
        executable,
        str(tmp_path.resolve()),
        "software-install",
        protocol_v2.ActionPhase.DOWNLOAD,
        ("--artifact", "sha256:" + "a" * 64),
        launcher=launcher,
        capability=capability,
    )
    assert downloaded.network.enforcement is protocol_v2.NetworkEnforcement.NOT_REQUESTED
    assert launcher.calls == []
    assert _object(downloaded.payload)["argv"] == [
        "software-install",
        "--phase",
        "download",
        "--target",
        str(tmp_path.resolve()),
        "--artifact",
        "sha256:" + "a" * 64,
    ]

    applied = invocation_v2.invoke(
        executable,
        str(tmp_path.resolve()),
        "software-install",
        protocol_v2.ActionPhase.APPLY,
        launcher=launcher,
        capability=capability,
    )
    assert applied.network.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
    assert len(launcher.calls) == 1
    assert "--phase" in launcher.calls[0]


@pytest.mark.skipif(
    platform.system() != "Linux" or shutil.which("bwrap") is None,
    reason="real Bubblewrap invocation requires an owned Linux runner with bwrap",
)
def test_real_local_provider_phase_cannot_reach_a_positive_control(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = cast(tuple[str, int], listener.getsockname())[1]
    executable = _provider(
        tmp_path,
        "import json, socket\n"
        "try:\n"
        f"    connection = socket.create_connection(('127.0.0.1', {port}), timeout=0.5)\n"
        "except OSError:\n"
        "    network = 'denied'\n"
        "else:\n"
        "    connection.close()\n"
        "    network = 'reachable'\n"
        "print(json.dumps({'network': network}))\n",
    )
    try:
        launcher, capability = network_launcher.discover_bubblewrap()
        assert launcher is not None, capability.evidence
        result = invocation_v2.invoke(
            executable,
            str(tmp_path.resolve()),
            "provider-info",
            protocol_v2.ActionPhase.EXECUTE,
            launcher=launcher,
            capability=capability,
        )
    finally:
        listener.close()

    assert _object(result.payload)["network"] == "denied"
    assert result.network.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
    assert result.network.launcher_id == capability.launcher_id


def test_v2_requires_an_existing_absolute_target(tmp_path: Path) -> None:
    executable = _provider(tmp_path, "print('{}')\n")

    with pytest.raises(ValueError, match="existing absolute directory"):
        invocation_v2.invoke(
            executable,
            "relative-target",
            "launch",
            protocol_v2.ActionPhase.EXECUTE,
            launcher=None,
            capability=None,
        )


def test_v3_core_always_uses_the_exact_enforced_local_launcher(tmp_path: Path) -> None:
    executable = _provider(
        tmp_path,
        "import json, sys\nprint(json.dumps({'argv': sys.argv[1:]}))\n",
    )
    capability = _enforced()
    launcher = RecordingLauncher(capability)

    info = invocation_v3.invoke(
        executable,
        str(tmp_path.resolve()),
        "provider-info",
        launcher=launcher,
        capability=capability,
    )
    status = invocation_v3.invoke(
        executable,
        str(tmp_path.resolve()),
        "status",
        ("--probe", "exact"),
        launcher=launcher,
        capability=capability,
    )

    assert _object(info)["argv"] == ["provider-info"]
    assert _object(status)["argv"] == [
        "status",
        "--target",
        str(tmp_path.resolve()),
        "--json",
        "--probe",
        "exact",
    ]
    assert len(launcher.calls) == 2


def test_v3_refuses_unknown_commands_and_unproved_network_isolation(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    executable = _provider(tmp_path, f"open({str(marker)!r}, 'w').write('yes')\nprint('{{}}')\n")

    with pytest.raises(KeyError, match="unknown provider v3 core command"):
        invocation_v3.invoke(
            executable,
            str(tmp_path.resolve()),
            "launch",
            launcher=None,
            capability=None,
        )
    with pytest.raises(protocol_v2.NetworkCapabilityUnavailable):
        invocation_v3.invoke(
            executable,
            str(tmp_path.resolve()),
            "status",
            launcher=None,
            capability=_enforced(),
        )
    with pytest.raises(ValueError, match="existing absolute directory"):
        invocation_v3.invoke(
            executable,
            "relative-target",
            "status",
            launcher=None,
            capability=None,
        )

    assert not marker.exists()
