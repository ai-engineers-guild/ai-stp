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
from typing import Any, NoReturn

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


def test_the_windows_probe_child_answers_in_the_shared_vocabulary() -> None:
    """Not the same text as the Linux child, and the same reading.

    The Windows child is PowerShell for the reason `WINDOWS_CHILD_PROBE` gives.
    What must not drift is the answer: the three keys and the words the parent
    compares against, so `_probe` on both platforms is one reading of one
    vocabulary rather than two probes that happen to agree today.
    """
    for word in ("ipv4", "ipv6", "dns_udp", "reachable", "denied", "sent", "send_failed"):
        assert f"'{word}'" in windows_launcher.WINDOWS_CHILD_PROBE, word
        assert f'"{word}"' in CHILD_PROBE, word
    assert "ai-stp-dns-probe" in windows_launcher.WINDOWS_CHILD_PROBE
    assert "ai-stp-dns-probe" in CHILD_PROBE
    tail = windows_launcher.encoded_command("Write-Output 1")
    assert tail[-2] == "-EncodedCommand"
    assert "Write-Output 1".encode("utf-16-le") == __import__("base64").b64decode(tail[-1])


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
    # Two files the argv names, outside the target and the runtime, as the
    # bundle handed to `validate-bundle` is: the script itself, run with
    # `-File` so it takes an argument, and the file that argument names. The
    # container must be able to read both, and only because they were named.
    # (`-EncodedCommand` takes no trailing argument; a first attempt passed
    # one and PowerShell answered a usage error instead of the script.)
    named_root = Path(os.environ["TEMP"]) / "ai-stp-appcontainer-named"
    named_root.mkdir(parents=True, exist_ok=True)
    named = named_root / "bundle.bin"
    named.write_text("named-bytes", encoding="utf-8")
    place = target / "written-inside"
    script = named_root / "probe.ps1"
    script.write_text(
        f"[System.IO.File]::WriteAllText('{place}', 'inside')\n"
        f"$written = [System.IO.File]::ReadAllText('{place}')\n"
        "$named = [System.IO.File]::ReadAllText($args[0])\n"
        "[System.Console]::Error.WriteLine('diagnostic noise that is not the answer')\n"
        "[System.Console]::Out.Write('{\"written\":')\n"
        "[System.Console]::Out.Flush()\n"
        "[System.Threading.Thread]::Sleep(400)\n"
        "[System.Console]::Out.WriteLine('\"' + $written + '\",\"named\":\"' + $named + '\"}')\n",
        encoding="utf-8",
    )
    answer = launcher.run(
        (
            str(windows_launcher.powershell()),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            str(named),
        ),
        target=target,
        command="probe",
    )
    assert answer == {"written": "inside", "named": "named-bytes"}, answer
    assert place.read_text(encoding="utf-8") == "inside"


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
sleeper = windows_launcher.encoded_command("[System.Threading.Thread]::Sleep(120000)")
launcher.run(
    (str(windows_launcher.powershell()), *sleeper),
    target=Path(sys.argv[1]),
    command="sleep",
)
"""


def _children_of(pid: int) -> list[int]:
    """Read the process tree from Toolhelp without the runner's WMI service."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    load_library: Any = vars(ctypes)["WinDLL"]
    kernel: Any = load_library("kernel32", use_last_error=True)
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return []
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    children: list[int] = []
    try:
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            if int(entry.th32ParentProcessID) == pid:
                children.append(int(entry.th32ProcessID))
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return children


def _alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    load_library: Any = vars(ctypes)["WinDLL"]
    kernel: Any = load_library("kernel32", use_last_error=True)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    exit_code = wintypes.DWORD()
    try:
        queried = kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return bool(queried) and exit_code.value == 259  # STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


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
        lease = windows_launcher._lease_path()  # pyright: ignore[reportPrivateUsage]
        leased = time.monotonic() + 30
        target_text = str(target.resolve())
        while time.monotonic() < leased:
            try:
                if target_text in lease.read_text(encoding="utf-8"):
                    break
            except OSError:
                pass
            time.sleep(0.25)
        else:
            pytest.fail("the grant was not durably leased before the parent kill")
    finally:
        parent.kill()
        parent.wait(timeout=60)

    gone = time.monotonic() + 30
    while time.monotonic() < gone and _alive(child):
        time.sleep(0.5)
    assert not _alive(child), "the isolated child outlived its parent"

    swept = windows_launcher.sweep_abandoned_grants()
    assert target_text in swept, swept
