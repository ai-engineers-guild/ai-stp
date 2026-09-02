"""The Windows AppContainer launcher, and what it refuses to claim.

`#51` asks for a launcher that denies the network by the device rather than by
agreement, and `ADR-0133` measured that an AppContainer does. What these tests
hold is the half a measurement cannot: that every path which is *not* a passed
probe reports `unavailable`, because `provider network` reporting `enforced` is
the one output somebody checks before trusting a local phase.

They run on every platform. On Linux and macOS the module is expected to refuse
by platform, which is itself worth pinning — a launcher that quietly reported
enforced off-Windows would be the same defect as one that reported it without a
probe.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

import pytest

from ai_stp_cli.provider import windows_launcher
from ai_stp_cli.provider.network_launcher import CHILD_PROBE
from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement

WINDOWS = platform.system().casefold() == "windows"


def test_the_launcher_refuses_to_exist_without_enforced_evidence() -> None:
    """A launcher is the object that says the denial was proved.

    Constructing one from an unavailable capability would let every later caller
    treat an unproved denial as a proved one, so it is refused at construction
    rather than checked at each use.
    """
    unproved = NetworkCapability(
        enforcement=NetworkEnforcement.UNAVAILABLE,
        os_name="windows",
        launcher_id=None,
        evidence=("nothing was measured",),
    )
    with pytest.raises(ValueError, match="enforced capability evidence"):
        windows_launcher.AppContainerLauncher(package_sid="S-1-15-2-1", capability=unproved)


def test_a_launcher_cannot_carry_another_principal_s_identity() -> None:
    """The identity names the principal the grants were made to.

    A launcher whose `launcher_id` does not derive from its own package SID
    would grant access to one container and start a process in another, which
    fails as a permission error rather than as an isolation one.
    """
    mismatched = NetworkCapability(
        enforcement=NetworkEnforcement.ENFORCED,
        os_name="windows",
        launcher_id="appcontainer:S-1-15-2-999",
        evidence=("probe passed",),
    )
    with pytest.raises(ValueError, match="launcher identity"):
        windows_launcher.AppContainerLauncher(package_sid="S-1-15-2-1", capability=mismatched)


@pytest.mark.skipif(WINDOWS, reason="off-Windows refusal is what this pins")
def test_off_windows_discovery_is_unavailable_and_names_why() -> None:
    """Not an error, and not silence: an unavailable capability with a reason.

    Linux has its own proved launcher and macOS has none; either way this one
    must not be the thing that answers, and it must say so rather than return a
    launcher nobody can use.
    """
    launcher, capability = windows_launcher.discover_appcontainer()
    assert launcher is None
    assert capability.enforcement is NetworkEnforcement.UNAVAILABLE
    assert capability.launcher_id is None
    assert "Windows-only" in capability.evidence[0]


def test_the_probe_child_is_the_same_text_the_linux_launcher_uses() -> None:
    """`#51` requires the same class of probe, and this is how that is kept true.

    Two texts that resemble each other drift; one text cannot. If this ever
    fails it means someone gave Windows its own child, and the claim that the
    two denials are established the same way stopped being true at that commit.
    """
    assert "ai-stp-dns-probe" in CHILD_PROBE
    # Reaching through the Windows module on purpose: that the name it holds
    # is the Linux module's object is the assertion, not an accident of import.
    assert CHILD_PROBE is windows_launcher.CHILD_PROBE  # pyright: ignore[reportPrivateImportUsage]


@pytest.mark.skipif(not WINDOWS, reason="exercises the real isolation boundary")
def test_the_isolated_spawn_reaches_the_target_and_not_the_network() -> None:
    """The end-to-end claim, on the platform that can refute it.

    Deliberately not a re-run of the probe: this drives the public `spawn`,
    which is what a provider invocation actually uses, including the grant of
    the target and the runtime and their removal afterwards.
    """
    launcher, capability = windows_launcher.discover_appcontainer()
    if launcher is None:
        _unproved(capability.evidence[0])
    assert capability.enforcement is NetworkEnforcement.ENFORCED
    assert capability.launcher_id == f"appcontainer:{launcher.package_sid}"

    target = Path(os.environ["TEMP"]) / "ai-stp-appcontainer-run"
    target.mkdir(parents=True, exist_ok=True)
    child = (
        "import json, pathlib, sys\n"
        "place = pathlib.Path(sys.argv[1]) / 'written-inside'\n"
        "place.write_text('inside', encoding='utf-8')\n"
        "print(json.dumps({'written': place.read_text(encoding='utf-8')}))\n"
    )
    answer = launcher.run(
        (_base_python(), "-c", child, str(target)), target=target, command="probe"
    )
    assert answer == {"written": "inside"}, answer
    assert (target / "written-inside").read_text(encoding="utf-8") == "inside"


def _base_python() -> str:
    """The interpreter a container can run: the base one, not a venv launcher."""
    return str(getattr(sys, "_base_executable", None) or sys.executable)


def _unproved(reason: str) -> NoReturn:
    """A hosted runner that cannot prove the AppContainer is a red result.

    This test skipped on every `windows-latest` run for a month while the
    launcher answered `[Errno 203]`, and a skip reads as green. Off CI an
    unproved host stays a legitimate outcome — a developer's box need not be
    elevated — but a GitHub runner is the environment `ADR-0133` measured, and
    there the only honest reading of "unproved" is a failure.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail(f"a hosted Windows runner did not prove the AppContainer: {reason}")
    pytest.skip(f"no proved AppContainer here: {reason}")


_HELPER = """
import sys
from pathlib import Path
from ai_stp_cli.provider import windows_launcher
launcher, capability = windows_launcher.discover_appcontainer()
if launcher is None:
    print("UNPROVED " + capability.evidence[0], flush=True)
    sys.exit(3)
print("READY", flush=True)
python = str(getattr(sys, "_base_executable", None) or sys.executable)
launcher.run(
    (python, "-c", "import time; time.sleep(120)"),
    target=Path(sys.argv[1]),
    command="sleep",
)
"""


def _children_of(pid: int) -> list[int]:
    found = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' "
            "| Select-Object -ExpandProperty ProcessId",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return [int(line) for line in found.stdout.split() if line.strip().isdigit()]


def _alive(pid: int) -> bool:
    found = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}') -ne $null",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return found.stdout.strip().casefold() == "true"


@pytest.mark.skipif(not WINDOWS, reason="exercises the real job object and the grant lease")
def test_a_killed_parent_takes_its_isolated_tree_and_its_grants_with_it(
    tmp_path: Path,
) -> None:
    """`ADR-0133`'s two obligations, measured under a real parent kill.

    The job object carries `KILL_ON_JOB_CLOSE`, so a parent that dies without
    running any cleanup still takes the provider tree with it; and the grant
    lease written before `icacls` runs lets the next discovery take back an ACE
    the dead parent never revoked. Both were implemented and unit-tested with
    fakes; this is the first run of either against the operating system.
    """
    target = tmp_path / "target"
    target.mkdir()
    script = tmp_path / "parent.py"
    script.write_text(_HELPER, encoding="utf-8")
    parent = subprocess.Popen(
        [sys.executable, str(script), str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    try:
        assert parent.stdout is not None
        first = parent.stdout.readline().strip()
        if first.startswith("UNPROVED"):
            parent.kill()
            _unproved(first.removeprefix("UNPROVED").strip())
        assert first == "READY", first
        deadline = time.monotonic() + 60
        grandchildren: list[int] = []
        while time.monotonic() < deadline and not grandchildren:
            grandchildren = _children_of(parent.pid)
            if not grandchildren:
                time.sleep(0.5)
        assert grandchildren, "the parent never started its isolated child"
        child = grandchildren[0]
        assert _alive(child)
    finally:
        parent.kill()
        parent.wait(timeout=60)

    gone = time.monotonic() + 30
    while time.monotonic() < gone and _alive(child):
        time.sleep(0.5)
    assert not _alive(child), "the isolated child outlived its parent"

    swept = windows_launcher.sweep_abandoned_grants()
    assert str(target.resolve()) in swept, swept
