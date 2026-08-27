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

    for reason in sorted(network_launcher.UNISOLATED_REASONS):
        assert network_launcher.unisolated_local_phase(reason).reason == reason


def test_the_exception_cannot_be_made_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """The permission is not a flag a caller can carry across platforms.

    Linux has a launcher that proves denial, so an unisolated phase there is not
    a concession to a missing capability — it is the capability being skipped.
    """
    _on(monkeypatch, "Linux")

    with pytest.raises(CliFailure) as raised:
        network_launcher.unisolated_local_phase("trusted_release")

    assert raised.value.details["os"] == "linux"
    assert "can deny the network" in raised.value.message


def test_every_launcherless_platform_can_build_the_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """macOS was missing, and nothing had decided it should be.

    `windows` was written into the name and into the platform check, so on macOS
    `discover_bubblewrap` returned nothing *and* the exception refused to be
    built — every v3 provider call refused, on a platform whose providers this
    CLI fetches and attests and whose jobs run in the gate matrix.

    The rule is about the platform, not about the name: a system that cannot
    deny the network gets the exception, a system that can does not. Linux is
    excluded because its missing `bwrap` is a missing dependency rather than a
    missing capability, and skipping a capability that exists is a different act
    from conceding one that does not.
    """
    for system in ("Windows", "Darwin"):
        _on(monkeypatch, system)
        held = network_launcher.unisolated_local_phase(network_launcher.TRUSTED_RELEASE)
        assert held.reason == network_launcher.TRUSTED_RELEASE, system
        _, capability = network_launcher.discover_bubblewrap()
        assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE, system

    _on(monkeypatch, "Linux")
    with pytest.raises(CliFailure):
        network_launcher.unisolated_local_phase(network_launcher.TRUSTED_RELEASE)


def test_a_reason_outside_the_closed_set_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch, "Windows")

    with pytest.raises(CliFailure):
        network_launcher.unisolated_local_phase("because the install needs it")


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
    permission = network_launcher.unisolated_local_phase("trusted_release")
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
    permission = network_launcher.unisolated_local_phase("trusted_release")
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
    # Compared through the module's own token function rather than `str`.
    # `wrap` renders paths the way bwrap wants them, which on Windows is not
    # what `Path.__str__` produces — and a test that spells the path itself is
    # asserting its own idea of a path rather than the code's.
    assert launcher_module._path_token(target.resolve()) in binds  # pyright: ignore[reportPrivateUsage]
    assert launcher_module._path_token(prefix.resolve()) in binds, (  # pyright: ignore[reportPrivateUsage]
        "the prefix is where the program goes"
    )


def _conformance_reasons(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Record the reason `provider conformance` hands the shared invoker."""
    seen: list[str | None] = []

    def invoker(
        executable: str,
        target: str,
        version: int,
        *,
        unisolated_reason: str | None = None,
        writable: tuple[Path, ...] = (),
    ) -> object:
        seen.append(unisolated_reason)
        raise _Stop

    monkeypatch.setattr("ai_stp_cli.provider.invocation.provider_invoker", invoker)
    return seen


class _Stop(Exception):
    """Ends the command once the reason has been observed."""


def test_conformance_asks_for_the_exception_only_when_the_operator_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ADR-0126`: the same gate as an install, not a read-only exemption.

    Refusing conformance while permitting install was inconsistent — the same
    provider, the same target, strictly fewer rights, refused. The difference
    that matters is whose executable it is, and this command can establish only
    one of the two answers: the operator's own `--unverified-provider`, because
    it reads no release manifest and takes whatever path it is handed.

    Asserted on the reason handed to the shared invoker rather than on a spawn,
    so the test states the decision instead of the platform's ability to run a
    file — which is how the Windows leg was broken by its own test once.
    """
    from ai_stp_cli.commands import select

    target = tmp_path / "target"
    target.mkdir()
    executable = tmp_path / "provider-stub"
    executable.write_text("stub", encoding="utf-8")
    executable.chmod(0o755)

    base = {
        "harness": "claude-code",
        "executable": str(executable),
        "target": str(target),
        "protocol-version": 3,
    }

    seen = _conformance_reasons(monkeypatch)
    with pytest.raises(_Stop):
        select.provider_conformance(base)
    assert seen == [None], "without the flag nothing is asked for, exactly as before"

    seen.clear()
    with pytest.raises(_Stop):
        select.provider_conformance({**base, "unverified-provider": True})
    assert seen == [network_launcher.EXPLICIT_UNVERIFIED_PROVIDER]

    # `trusted_release` is the other reason `#416` accepts, and conformance must
    # never claim it: no manifest was read, so the claim would be unfounded.
    assert network_launcher.TRUSTED_RELEASE not in seen


def test_the_observers_ask_on_the_same_named_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ADR-0126`'s amendment: a rule, not a list that grows by one per commit.

    `target status` and `target diff` take an arbitrary `--provider` exactly as
    conformance does, and on Windows they did not run at all — the same hole in
    the platform. They read rather than write, which is precisely the wrong
    distinction: an unisolated phase is already permitted for the install that
    *changes* the same live target.

    Both observers went through one identical block, so the decision would have
    had to be remembered twice. It is one function now, and this asserts the
    reason it hands over — for both commands, and only when asked.
    """
    from ai_stp_cli.commands import install

    executable = tmp_path / "provider-stub"
    executable.write_text("stub", encoding="utf-8")
    executable.chmod(0o755)
    target = tmp_path / "target"
    target.mkdir()

    seen: list[str | None] = []

    def invoker(
        _executable: str,
        _target: str,
        _version: int,
        *,
        unisolated_reason: str | None = None,
        writable: tuple[Path, ...] = (),
    ) -> object:
        seen.append(unisolated_reason)
        raise _Stop

    monkeypatch.setattr("ai_stp_cli.provider.invocation.provider_invoker", invoker)

    # Both observers answer from local state alone when no registry exists, and
    # return before reaching a provider at all. The file only has to be there;
    # the invoker is called before anything reads it.
    from contextlib import closing

    from ai_stp_cli.local.database import configured_path, open_registry

    with closing(open_registry(configured_path(), create=True)):
        pass

    base = {
        "project": "project_01ABCDEFGHJKMNPQRSTVWXYZ00",
        "harness": "claude-code",
        "provider": str(executable),
        "protocol-version": 3,
        "target": str(target),
    }
    for handler in (install.target_status, install.target_diff):
        seen.clear()
        with pytest.raises(_Stop):
            handler(dict(base))
        assert seen == [None], handler.__name__

        seen.clear()
        with pytest.raises(_Stop):
            handler({**base, "unverified-provider": True})
        assert seen == [network_launcher.EXPLICIT_UNVERIFIED_PROVIDER], handler.__name__
