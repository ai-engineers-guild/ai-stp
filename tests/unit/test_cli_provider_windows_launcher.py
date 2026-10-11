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

import ctypes
import json
import os
import platform
import queue
import subprocess
import sys
import threading
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
import ctypes
import sys
from dataclasses import replace
from pathlib import Path
from ai_stp_cli.provider import windows_launcher
launcher, capability = windows_launcher.discover_appcontainer()
if launcher is None:
    print("UNPROVED " + capability.evidence[0], flush=True)
    sys.exit(3)
api = windows_launcher._Api.load()
class HeldCreation:
    def __getattr__(self, name):
        return getattr(api.kernel, name)

    def CreateProcessW(self, *args):
        created = api.kernel.CreateProcessW(*args)
        if created:
            information = ctypes.cast(
                args[-1], ctypes.POINTER(windows_launcher._ProcessInformation)
            ).contents
            print("READY " + str(information.dwProcessId), flush=True)
            # Hold the parent inside process creation, before any later job
            # assignment or ResumeThread could conceal the ownership gap.
            sys.stdin.buffer.read(1)
        return created
windows_launcher._Api.load = classmethod(lambda cls: replace(api, kernel=HeldCreation()))
sleeper = windows_launcher.encoded_command("[System.Threading.Thread]::Sleep(120000)")
launcher.run(
    (str(windows_launcher.powershell()), *sleeper),
    target=Path(sys.argv[1]),
    command="sleep",
)
"""


@pytest.mark.skipif(not WINDOWS, reason="exercises the real job object and the grant lease")
def test_a_killed_parent_takes_its_isolated_tree_and_its_grants_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child already belongs to the job before CreateProcessW returns.

    The helper stops at that exact boundary. A retained native process handle
    identifies the observed child even after its PID could have been reused.
    The isolated lease also proves recovery after the parent skips cleanup.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    target = tmp_path / "target"
    target.mkdir()
    script = tmp_path / "parent.py"
    script.write_text(_HELPER, encoding="utf-8")
    load_library: Any = vars(ctypes)["WinDLL"]
    kernel: Any = load_library("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.TerminateProcess.restype = ctypes.c_int32
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int32
    child = None
    parent = subprocess.Popen(
        [sys.executable, str(script), str(target)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    try:
        try:
            assert parent.stdout is not None
            output = parent.stdout
            ready: queue.Queue[str] = queue.Queue()
            reader = threading.Thread(target=lambda: ready.put(output.readline()), daemon=True)
            reader.start()
            first = ready.get(timeout=60).strip()
            if first.startswith("UNPROVED"):
                _unproved(first.removeprefix("UNPROVED").strip())
            assert first.startswith("READY "), first
            pid = int(first.removeprefix("READY "))
            # SYNCHRONIZE observes termination; PROCESS_TERMINATE allows this
            # test to clean up its own child even when the regression fails.
            child = kernel.OpenProcess(0x00100001, False, pid)
            assert child, f"the created child {pid} could not be opened"
            assert kernel.WaitForSingleObject(child, 0) == 258, "the child is not waiting"
            lease = windows_launcher._lease_path()  # pyright: ignore[reportPrivateUsage]
            paths = {
                json.loads(line).get("path")
                for line in lease.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
            target_text = str(target.resolve())
            assert target_text in paths, "the grant was not leased before process creation"
        finally:
            parent.kill()
            parent.wait(timeout=60)
            if parent.stdin is not None:
                parent.stdin.close()
            if parent.stdout is not None:
                parent.stdout.close()

        assert kernel.WaitForSingleObject(child, 30_000) == 0, (
            "the isolated child outlived its parent before CreateProcessW returned"
        )
        swept = windows_launcher.sweep_abandoned_grants()
        assert target_text in swept, swept
    finally:
        if child is not None:
            kernel.TerminateProcess(child, 1)
            kernel.WaitForSingleObject(child, 30_000)
            kernel.CloseHandle(child)
        windows_launcher.sweep_abandoned_grants()
