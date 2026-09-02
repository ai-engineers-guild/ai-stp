"""macOS sandbox-exec is capability only after the native denial probe."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from ai_stp_cli.provider import macos_launcher, network_launcher, protocol_v2


def _capability(executable: Path = macos_launcher.EXECUTABLE) -> protocol_v2.NetworkCapability:
    return protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="darwin",
        launcher_id=f"sandbox-exec:{executable.as_posix()}",
        evidence=("observed",),
    )


def _completed(results: dict[str, str]) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess([], 0, json.dumps(results), "")

    return run


def _ignore_positive_control(*_args: object) -> None:
    return None


def _darwin() -> str:
    return "Darwin"


def _digest(_path: Path) -> str:
    return "a" * 64


def _passed_probe(_path: Path) -> tuple[bool, tuple[str, ...]]:
    return True, ("positive control passed", "network denied")


def _passed_write_probe(_path: Path) -> tuple[bool, tuple[str, ...]]:
    return True, ("write control passed", "write outside denied")


def _failed_write_probe(_path: Path) -> tuple[bool, tuple[str, ...]]:
    return False, ("writes were not bounded by the profile: {...}",)


def _answers(*results: dict[str, str]) -> Callable[..., subprocess.CompletedProcess[str]]:
    """One completed process per call, in order: the control first, then the profiled child."""
    queue = list(results)

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return subprocess.CompletedProcess([], 0, json.dumps(queue.pop(0)), "")

    return run


def test_constructor_requires_enforcement_and_matching_identity() -> None:
    unavailable = protocol_v2.NetworkCapability(
        protocol_v2.NetworkEnforcement.UNAVAILABLE,
        "darwin",
        None,
        ("missing",),
    )
    with pytest.raises(ValueError, match="requires enforced"):
        macos_launcher.SandboxExecLauncher(macos_launcher.EXECUTABLE, unavailable)
    with pytest.raises(ValueError, match="identity"):
        macos_launcher.SandboxExecLauncher(Path("/bin/false"), _capability())


def test_wrap_uses_the_closed_network_profile_and_exact_argv(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    provider = tmp_path / "provider"
    provider.write_text("provider", encoding="utf-8")
    launcher = macos_launcher.SandboxExecLauncher(macos_launcher.EXECUTABLE, _capability())

    wrapped = launcher.wrap((str(provider.resolve()), "status"), target=target.resolve())

    # The profile is now built per invocation, because it names the target and
    # every path the caller declared writable. It was a constant while writes
    # were unbounded, and that is exactly what made `writable` mean nothing here.
    assert wrapped == (
        "/usr/bin/sandbox-exec",
        "-p",
        macos_launcher.profile_for(target.resolve(), ()),
        str(provider.resolve()),
        "status",
    )
    assert "(deny network*)" in wrapped[2]
    assert "(deny file-write*)" in wrapped[2]


def test_probe_requires_all_three_transports_to_be_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(network_launcher, "positive_control", _ignore_positive_control)
    monkeypatch.setattr(
        "ai_stp_cli.provider.macos_launcher.subprocess.run",
        _completed({"dns_udp": "sent", "ipv4": "denied", "ipv6": "denied"}),
    )

    passed, evidence = macos_launcher._probe(  # pyright: ignore[reportPrivateUsage]
        macos_launcher.EXECUTABLE
    )

    assert passed, evidence

    monkeypatch.setattr(
        "ai_stp_cli.provider.macos_launcher.subprocess.run",
        _completed({"dns_udp": "sent", "ipv4": "reachable", "ipv6": "denied"}),
    )
    passed, evidence = macos_launcher._probe(  # pyright: ignore[reportPrivateUsage]
        macos_launcher.EXECUTABLE
    )
    assert not passed
    assert "network remained reachable" in evidence[0]


def test_discovery_remains_unavailable_without_a_trusted_probed_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ai_stp_cli.provider.macos_launcher.platform.system", _darwin)
    monkeypatch.setattr(
        macos_launcher,
        "_trusted_executable",
        lambda: (None, "sandbox-exec is absent"),
    )

    launcher, capability = macos_launcher.discover_sandbox_exec()

    assert launcher is None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE
    assert capability.evidence == ("sandbox-exec is absent",)


def test_passed_probe_constructs_the_enforced_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ai_stp_cli.provider.macos_launcher.platform.system", _darwin)
    monkeypatch.setattr(
        macos_launcher,
        "_trusted_executable",
        lambda: (macos_launcher.EXECUTABLE, None),
    )
    monkeypatch.setattr(macos_launcher, "_digest", _digest)
    monkeypatch.setattr(macos_launcher, "_probe", _passed_probe)
    monkeypatch.setattr(macos_launcher, "_write_probe", _passed_write_probe)

    launcher, capability = macos_launcher.discover_sandbox_exec()

    assert launcher is not None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
    assert capability.launcher_id == "sandbox-exec:/usr/bin/sandbox-exec"
    assert "sha256=" + "a" * 64 in capability.evidence
    assert "write outside denied" in capability.evidence


def test_a_network_probe_alone_does_not_make_the_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write claim in the evidence is measured, not inherited from the network one."""
    monkeypatch.setattr("ai_stp_cli.provider.macos_launcher.platform.system", _darwin)
    monkeypatch.setattr(
        macos_launcher,
        "_trusted_executable",
        lambda: (macos_launcher.EXECUTABLE, None),
    )
    monkeypatch.setattr(macos_launcher, "_digest", _digest)
    monkeypatch.setattr(macos_launcher, "_probe", _passed_probe)
    monkeypatch.setattr(macos_launcher, "_write_probe", _failed_write_probe)

    launcher, capability = macos_launcher.discover_sandbox_exec()

    assert launcher is None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE
    assert capability.evidence[0].startswith("writes were not bounded")


def test_write_probe_requires_the_control_to_write_both_and_the_profile_to_deny_outside(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_stp_cli.provider.macos_launcher.subprocess.run",
        _answers(
            {"inside": "written", "outside": "written"},
            {"inside": "written", "outside": "denied"},
        ),
    )
    passed, evidence = macos_launcher._write_probe(  # pyright: ignore[reportPrivateUsage]
        macos_launcher.EXECUTABLE
    )
    assert passed, evidence
    assert "denied the one outside" in evidence[1]

    monkeypatch.setattr(
        "ai_stp_cli.provider.macos_launcher.subprocess.run",
        _answers(
            {"inside": "written", "outside": "written"},
            {"inside": "written", "outside": "written"},
        ),
    )
    passed, evidence = macos_launcher._write_probe(  # pyright: ignore[reportPrivateUsage]
        macos_launcher.EXECUTABLE
    )
    assert not passed
    assert "writes were not bounded by the profile" in evidence[0]

    monkeypatch.setattr(
        "ai_stp_cli.provider.macos_launcher.subprocess.run",
        _answers({"inside": "written", "outside": "denied"}),
    )
    passed, evidence = macos_launcher._write_probe(  # pyright: ignore[reportPrivateUsage]
        macos_launcher.EXECUTABLE
    )
    assert not passed
    assert "write positive control failed" in evidence[0]


@pytest.mark.skipif(platform.system().casefold() != "darwin", reason="the real sandbox")
def test_the_real_sandbox_bounds_a_provider_s_writes_to_its_target(tmp_path: Path) -> None:
    """`ADR-0126`'s macOS half, measured: the deny-write profile against a real child.

    A hosted macOS runner is the environment the profile was written for, so an
    unproved launcher there is a red result rather than a skip.
    """
    launcher, capability = macos_launcher.discover_sandbox_exec()
    if launcher is None:
        reason = capability.evidence[0]
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail(f"a hosted macOS runner did not prove sandbox-exec: {reason}")
        pytest.skip(f"no proved sandbox-exec here: {reason}")
    target = tmp_path / "target"
    target.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    child = (
        "import json, pathlib, sys\n"
        "answer = {}\n"
        "for name, place in (('inside', sys.argv[1]), ('outside', sys.argv[2])):\n"
        "    try:\n"
        "        (pathlib.Path(place) / 'probe').write_text('x', encoding='utf-8')\n"
        "    except OSError:\n"
        "        answer[name] = 'denied'\n"
        "    else:\n"
        "        answer[name] = 'written'\n"
        "print(json.dumps(answer))\n"
    )
    answer = launcher.run(
        (sys.executable, "-c", child, str(target), str(elsewhere)), target=target, command="probe"
    )
    assert answer == {"inside": "written", "outside": "denied"}, answer
    assert (target / "probe").exists()
    assert not (elsewhere / "probe").exists()


def test_platform_router_uses_the_macos_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = macos_launcher.SandboxExecLauncher(macos_launcher.EXECUTABLE, _capability())
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.platform.system", _darwin)
    monkeypatch.setattr(
        macos_launcher,
        "discover_sandbox_exec",
        lambda: (expected, expected.capability),
    )

    launcher, capability = network_launcher.discover_launcher()

    assert launcher is expected
    assert capability == expected.capability


def test_probe_argv_uses_the_current_python_and_shared_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: tuple[str, ...] | None = None

    def run(argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal observed
        del kwargs
        observed = argv
        return subprocess.CompletedProcess(
            argv,
            0,
            json.dumps({"dns_udp": "sent", "ipv4": "denied", "ipv6": "denied"}),
            "",
        )

    monkeypatch.setattr(network_launcher, "positive_control", _ignore_positive_control)
    monkeypatch.setattr("ai_stp_cli.provider.macos_launcher.subprocess.run", run)

    passed, _evidence = macos_launcher._probe(  # pyright: ignore[reportPrivateUsage]
        macos_launcher.EXECUTABLE
    )

    assert passed
    assert observed is not None
    assert observed[:3] == ("/usr/bin/sandbox-exec", "-p", macos_launcher.PROFILE)
    assert sys.executable in observed
    assert network_launcher.CHILD_PROBE in observed
