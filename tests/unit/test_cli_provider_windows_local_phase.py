"""Windows runs a local phase without a network-denying launcher, and says so.

Linux proves network denial with Bubblewrap: a network namespace blocks the
socket and a bind mount hands over the target without touching host ACLs.
Windows 11 has no equivalent a plain CLI may use — AppContainer blocks the
network but reaching an arbitrary target needs DACL traversal, and preparing a
parent or a drive root is not something an installer gets to do.

So the provider refused before its first spawn, and nothing worked on Windows at
all. This is the deliberate exception, and everything here is about keeping it
exactly as narrow as it was decided to be.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import network_launcher, protocol_v2
from ai_stp_foundation.canonical import JsonValue


def _on(monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.platform.system", lambda: system)


def test_windows_may_run_a_local_phase_for_a_named_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch, "Windows")

    for reason in sorted(network_launcher.WINDOWS_UNISOLATED_REASONS):
        assert network_launcher.windows_unisolated(reason).reason == reason


def test_the_exception_cannot_be_made_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """The permission is not a flag a caller can carry across platforms.

    Linux has a launcher that proves denial, so an unisolated phase there is not
    a concession to a missing capability — it is the capability being skipped.
    """
    _on(monkeypatch, "Linux")

    with pytest.raises(CliFailure) as raised:
        network_launcher.windows_unisolated("trusted_release")

    assert "windows" in raised.value.message.lower()


def test_a_reason_outside_the_closed_set_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch, "Windows")

    with pytest.raises(CliFailure):
        network_launcher.windows_unisolated("because the install needs it")


def test_windows_capability_still_reports_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """`provider network` keeps saying the truth: nothing is enforcing anything.

    The exception is a decision to proceed without isolation, not a claim to
    have it. Reporting `enforced` here would make the security debt invisible in
    exactly the output an operator would check for it.
    """
    _on(monkeypatch, "Windows")

    launcher, capability = network_launcher.discover_bubblewrap()

    assert launcher is None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE
    assert capability.launcher_id is None


def _stub(tmp_path: Path) -> Path:
    """A file that exists and is never run.

    The refusal under test happens before any spawn, so this only has to be
    resolvable. It is deliberately not a shell script: a `#!/bin/sh` stub is
    executable on two of the three systems this suite runs on, and writing one
    here is how the Windows leg failed once already.
    """
    script = tmp_path / "provider-stub"
    script.write_text("stub", encoding="utf-8")
    # Executable because `resolve_executable` requires it on POSIX; the bit is a
    # no-op on Windows, where resolution is by existence. Content is not a
    # script, so nothing can accidentally run it on either.
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_without_isolation_and_without_the_exception_nothing_spawns(tmp_path: Path) -> None:
    """The refusal that made Windows unusable is still the default everywhere."""
    from ai_stp_cli.provider import invocation_v3

    target = tmp_path / "target"
    target.mkdir()

    with pytest.raises(protocol_v2.NetworkCapabilityUnavailable):
        invocation_v3.invoke(
            str(_stub(tmp_path)),
            str(target),
            "status",
            (),
            launcher=None,
            capability=None,
        )


def test_linux_may_not_use_the_exception_even_if_one_is_handed_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Built on Windows, carried to Linux, still refused.

    The value cannot normally be made off Windows, so this asserts the second
    line of defence: the place that consumes it re-checks the platform rather
    than trusting that construction was the only gate.
    """
    from ai_stp_cli.provider import invocation_v3

    _on(monkeypatch, "Windows")
    permission = network_launcher.windows_unisolated("trusted_release")
    _on(monkeypatch, "Linux")
    monkeypatch.setattr("ai_stp_cli.provider.invocation_v3.platform.system", lambda: "Linux")

    target = tmp_path / "target"
    target.mkdir()

    with pytest.raises(protocol_v2.NetworkCapabilityUnavailable):
        invocation_v3.invoke(
            str(_stub(tmp_path)),
            str(target),
            "status",
            (),
            launcher=None,
            capability=None,
            unisolated=permission,
        )


def test_windows_with_the_exception_reaches_the_spawn_unwrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the whole change: on Windows the call is no longer refused.

    Before this, `discover_bubblewrap` returned nothing on Windows and every v3
    provider spawn failed before it started, so no backup of a live harness
    target could be taken and the Windows end-to-end could not begin.

    What is asserted is the decision and the argv, not the operating system's
    ability to run a script. The first version of this test wrote a `#!/bin/sh`
    stub, which is executable on two of the three systems this must work on —
    so the test proving Windows works was the one that failed on Windows, with
    `WinError 193`. Patching the spawn keeps the assertion about the thing that
    changed: no wrapper, and no refusal.
    """
    from ai_stp_cli.provider import conformance, invocation_v3

    _on(monkeypatch, "Windows")
    permission = network_launcher.windows_unisolated("trusted_release")
    monkeypatch.setattr("ai_stp_cli.provider.invocation_v3.platform.system", lambda: "Windows")

    target = tmp_path / "target"
    target.mkdir()
    executable = tmp_path / "provider-stub"
    executable.write_text("stub", encoding="utf-8")

    seen: list[tuple[str, ...]] = []

    def spawn(argv: tuple[str, ...], *, command: str) -> JsonValue:
        seen.append(tuple(argv))
        return {"state": "missing", "target_digest": "x", "command": command}

    monkeypatch.setattr(conformance, "invoke_argv", spawn)

    def resolve(given: str) -> str:
        return str(Path(given).resolve())

    monkeypatch.setattr(conformance, "resolve_executable", resolve)

    answer = invocation_v3.invoke(
        str(executable),
        str(target),
        "status",
        (),
        launcher=None,
        capability=None,
        unisolated=permission,
    )

    assert isinstance(answer, dict)
    assert answer["state"] == "missing"
    assert len(seen) == 1
    argv = seen[0]
    # The provider itself, not a launcher in front of it. That absence is the
    # whole exception, and it is what `provider network` keeps reporting.
    assert argv[0] == str(executable.resolve())
    assert "bwrap" not in " ".join(argv)
    assert "--target" in argv and "--json" in argv


def test_a_program_operation_binds_its_prefix_writable(tmp_path: Path) -> None:
    """The sandbox is built for a setup, which has exactly one writable path.

    A program operation has two: the target it is told about, and the prefix it
    actually writes into. Binding only the target made the provider write its
    program into the sandbox's own `/tmp` tmpfs, where everything it then
    checked was true — so it reported `verified` for files that ceased to exist
    when the namespace did.

    That is the worst shape a defect can take: a truthful provider, a passing
    check, and nothing on disk.
    """
    from ai_stp_cli.provider import network_launcher as launcher_module

    target = tmp_path / "target"
    target.mkdir()
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    executable = tmp_path / "provider"
    executable.write_text("stub", encoding="utf-8")

    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="linux",
        launcher_id="bubblewrap:/usr/bin/bwrap",
        evidence=("probed",),
    )
    launcher = launcher_module.BubblewrapLauncher(
        executable=Path("/usr/bin/bwrap"), capability=capability
    )

    wrapped = launcher.wrap((str(executable), "apply-operation"), target=target, writable=(prefix,))

    binds = [
        wrapped[index + 1]
        for index, item in enumerate(wrapped)
        if item == "--bind" and index + 1 < len(wrapped)
    ]
    assert str(target.resolve()) in binds
    assert str(prefix.resolve()) in binds, "the prefix is where the program goes"
