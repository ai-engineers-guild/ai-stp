"""Linux network capability is observed and every missing proof fails closed."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai_stp_cli.provider import network_launcher, protocol_v2


def _capability(executable: Path = Path("/usr/bin/bwrap")) -> protocol_v2.NetworkCapability:
    return protocol_v2.NetworkCapability(
        protocol_v2.NetworkEnforcement.ENFORCED,
        "linux",
        f"bubblewrap:{executable.as_posix()}",
        ("observed",),
    )


def _ignore_positive_control(*_args: object) -> None:
    return None


def _completed_runner(
    completed: subprocess.CompletedProcess[str],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        del _args, _kwargs
        return completed

    return run


def test_absent_bubblewrap_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(_name: str) -> None:
        return None

    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.platform.system", lambda: "Linux")
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.shutil.which", missing)

    launcher, capability = network_launcher.discover_bubblewrap()

    assert launcher is None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE
    assert capability.launcher_id is None


def test_non_linux_never_claims_the_linux_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.platform.system", lambda: "Darwin")

    launcher, capability = network_launcher.discover_bubblewrap()

    assert launcher is None
    assert capability.os_name == "darwin"
    assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE


@pytest.mark.skipif(os.name == "nt", reason="Bubblewrap ownership probe is Linux-only")
@pytest.mark.unprivileged
def test_user_controlled_bubblewrap_is_refused_before_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "bwrap"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.platform.system", lambda: "Linux")

    def found(_name: str) -> str:
        return str(executable)

    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.shutil.which", found)

    def forbidden(_executable: Path) -> tuple[bool, tuple[str, ...]]:
        raise AssertionError("an untrusted launcher must not execute its probe")

    monkeypatch.setattr(network_launcher, "_probe_bubblewrap", forbidden)

    launcher, capability = network_launcher.discover_bubblewrap()

    assert launcher is None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE
    assert any("not root-owned" in item for item in capability.evidence)


def test_launcher_refuses_relative_executable_or_target(tmp_path: Path) -> None:
    capability = _capability()
    launcher = network_launcher.BubblewrapLauncher(Path("/usr/bin/bwrap"), capability)

    with pytest.raises(ValueError, match="executable must be absolute"):
        launcher.wrap(("provider", "status"), target=tmp_path)
    with pytest.raises(ValueError, match="target must be"):
        launcher.wrap((sys.executable, "status"), target=Path("relative"))


def test_launcher_identity_and_enforcement_are_constructor_invariants() -> None:
    unavailable = protocol_v2.NetworkCapability(
        protocol_v2.NetworkEnforcement.UNAVAILABLE, "linux", None, ("absent",)
    )
    with pytest.raises(ValueError, match="requires enforced"):
        network_launcher.BubblewrapLauncher(Path("/usr/bin/bwrap"), unavailable)
    with pytest.raises(ValueError, match="identity"):
        network_launcher.BubblewrapLauncher(Path("/usr/bin/bwrap"), _capability(Path("/bin/false")))


def test_wrap_binds_exact_inputs_read_only_and_only_the_target_writable(tmp_path: Path) -> None:
    """Wrap argv is pure path logic; runs on Windows with a fake bwrap path."""
    bwrap = tmp_path / "bwrap"
    bwrap.write_text("", encoding="utf-8")
    provider = tmp_path / "provider"
    provider.write_text("provider", encoding="utf-8")
    bundle = tmp_path / "bundle.zip"
    bundle.write_text("bundle", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    launcher = network_launcher.BubblewrapLauncher(bwrap, _capability(bwrap))

    command = launcher.wrap(
        (str(provider.resolve()), str(bundle.resolve()), str(bundle.resolve()), "status"),
        target=target.resolve(),
    )

    assert command[0] == network_launcher._path_token(bwrap)  # pyright: ignore[reportPrivateUsage]
    provider_token = network_launcher._path_token(provider.resolve())  # pyright: ignore[reportPrivateUsage]
    bundle_token = network_launcher._path_token(bundle.resolve())  # pyright: ignore[reportPrivateUsage]
    # ro-bind mounts use path tokens; trailing argv keeps original path strings.
    assert provider_token in command
    assert bundle_token in command
    assert "--ro-bind" in command
    assert command[-4:] == (
        str(provider.resolve()),
        str(bundle.resolve()),
        str(bundle.resolve()),
        "status",
    )
    bind = command.index("--bind")
    target_token = network_launcher._path_token(target.resolve())  # pyright: ignore[reportPrivateUsage]
    assert command[bind : bind + 3] == ("--bind", target_token, target_token)

    if os.name != "nt":
        linked = tmp_path / "linked-target"
        linked.symlink_to(target, target_is_directory=True)
        with pytest.raises(ValueError, match="target must be"):
            launcher.wrap((str(provider.resolve()),), target=linked)


def test_digest_streams_the_exact_file(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"a" * (1024 * 1024 + 3))
    assert (
        network_launcher._digest(artifact)  # pyright: ignore[reportPrivateUsage]
        == hashlib.sha256(artifact.read_bytes()).hexdigest()
    )


def test_system_path_refusals_are_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    executable = Path("/owned/bin/bwrap")

    def writable(path: Path, *args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        mode = stat.S_IFREG | 0o777 if path == executable else stat.S_IFDIR | 0o755
        return SimpleNamespace(st_uid=0, st_mode=mode)

    monkeypatch.setattr(Path, "stat", writable)
    assert "group/world writable" in str(
        network_launcher._system_path_refusal(executable)  # pyright: ignore[reportPrivateUsage]
    )

    def unreadable(_path: Path, *args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        raise PermissionError("refused")

    monkeypatch.setattr(Path, "stat", unreadable)
    assert "cannot inspect" in str(
        network_launcher._system_path_refusal(executable)  # pyright: ignore[reportPrivateUsage]
    )

    def regular_file(_path: Path, *args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o755)

    def inaccessible(_path: object, _mode: int) -> bool:
        return False

    monkeypatch.setattr(Path, "stat", regular_file)
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.os.access", inaccessible)
    assert (
        network_launcher._system_path_refusal(  # pyright: ignore[reportPrivateUsage]
            executable
        )
        == "bwrap is not an executable regular file"
    )

    def executable_only(_path: Path, *args: object, **kwargs: object) -> SimpleNamespace:
        del args, kwargs
        mode = stat.S_IFREG | 0o755
        return SimpleNamespace(st_uid=0, st_mode=mode)

    def accessible(_path: object, _mode: int) -> bool:
        return True

    monkeypatch.setattr(Path, "stat", executable_only)
    monkeypatch.setattr("ai_stp_cli.provider.network_launcher.os.access", accessible)
    assert "ancestor is not a directory" in str(
        network_launcher._system_path_refusal(executable)  # pyright: ignore[reportPrivateUsage]
    )


def test_probe_socket_helpers_prove_the_positive_control() -> None:
    ipv4 = network_launcher.listener(socket.AF_INET, "127.0.0.1")
    try:
        ipv6 = network_launcher.listener(socket.AF_INET6, "::1")
    except OSError:
        ipv4.close()
        pytest.skip("this host has no IPv6 loopback")
    dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns.bind(("127.0.0.1", 0))
    try:
        assert network_launcher.port(ipv4) > 0
        network_launcher.positive_control(ipv4, ipv6, dns)
    finally:
        ipv4.close()
        ipv6.close()
        dns.close()

    class InvalidSocket:
        def getsockname(self) -> str:
            return "not-an-address"

    with pytest.raises(OSError, match="numeric port"):
        network_launcher.port(cast(socket.socket, InvalidSocket()))


@pytest.mark.parametrize(
    ("completed", "expected"),
    [
        (subprocess.CompletedProcess([], 1, "", "first\nlast"), "last"),
        (subprocess.CompletedProcess([], 0, "not-json", ""), "invalid JSON"),
        (
            subprocess.CompletedProcess(
                [], 0, '{"dns_udp":"denied","ipv4":"reachable","ipv6":"denied"}', ""
            ),
            "network remained reachable",
        ),
    ],
)
def test_probe_refuses_bad_child_results(
    completed: subprocess.CompletedProcess[str],
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(network_launcher, "positive_control", _ignore_positive_control)
    monkeypatch.setattr(subprocess, "run", _completed_runner(completed))
    passed, evidence = network_launcher._probe_bubblewrap(Path("/usr/bin/bwrap"))  # pyright: ignore[reportPrivateUsage]
    assert not passed
    assert expected in evidence[0]


def test_probe_accepts_only_the_exact_denial_result(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(
        [], 0, '{"dns_udp":"sent","ipv4":"denied","ipv6":"denied"}', ""
    )
    monkeypatch.setattr(network_launcher, "positive_control", _ignore_positive_control)
    monkeypatch.setattr(subprocess, "run", _completed_runner(completed))
    passed, evidence = network_launcher._probe_bubblewrap(Path("/usr/bin/bwrap"))  # pyright: ignore[reportPrivateUsage]
    assert passed
    assert evidence == (
        "positive control reached IPv4, IPv6 and DNS UDP endpoints",
        "network namespace denied IPv4, IPv6 and DNS UDP transports",
    )


def test_probe_failures_never_become_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network_launcher, "positive_control", _ignore_positive_control)

    def timed_out(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("bwrap", 3)

    monkeypatch.setattr(subprocess, "run", timed_out)
    passed, evidence = network_launcher._probe_bubblewrap(Path("/usr/bin/bwrap"))  # pyright: ignore[reportPrivateUsage]
    assert not passed
    assert "probe failed" in evidence[0]

    def no_socket(*_args: object, **_kwargs: object) -> socket.socket:
        raise OSError("no socket")

    monkeypatch.setattr(network_launcher, "listener", no_socket)
    passed, evidence = network_launcher._probe_bubblewrap(Path("/usr/bin/bwrap"))  # pyright: ignore[reportPrivateUsage]
    assert not passed
    assert "positive-control socket unavailable" in evidence[0]


def test_discovery_returns_a_launcher_only_after_every_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = Path("/usr/bin/bwrap")
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    def found(_name: str) -> str:
        return str(executable)

    monkeypatch.setattr(shutil, "which", found)

    def trusted_path(_path: Path) -> None:
        return None

    def exact_digest(_path: Path) -> str:
        return "a" * 64

    def successful_probe(_path: Path) -> tuple[bool, tuple[str, ...]]:
        return True, ("positive control", "network denied")

    monkeypatch.setattr(network_launcher, "_system_path_refusal", trusted_path)
    monkeypatch.setattr(network_launcher, "_digest", exact_digest)
    monkeypatch.setattr(
        network_launcher,
        "_probe_bubblewrap",
        successful_probe,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        _completed_runner(subprocess.CompletedProcess([], 0, "bubblewrap 1.0\n", "")),
    )

    launcher, capability = network_launcher.discover_bubblewrap()

    assert launcher is not None
    assert capability.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
    assert capability.evidence == (
        "version=bubblewrap 1.0",
        "sha256=" + "a" * 64,
        "positive control",
        "network denied",
    )


def test_discovery_refuses_identification_and_probe_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = Path("/usr/bin/bwrap")
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    def found(_name: str) -> str:
        return str(executable)

    monkeypatch.setattr(shutil, "which", found)

    def trusted_path(_path: Path) -> None:
        return None

    monkeypatch.setattr(network_launcher, "_system_path_refusal", trusted_path)

    def cannot_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("cannot run")

    monkeypatch.setattr(subprocess, "run", cannot_run)
    launcher, capability = network_launcher.discover_bubblewrap()
    assert launcher is None
    assert "cannot identify" in capability.evidence[0]

    def exact_digest(_path: Path) -> str:
        return "a" * 64

    def failed_probe(_path: Path) -> tuple[bool, tuple[str, ...]]:
        return False, ("denial",)

    monkeypatch.setattr(network_launcher, "_digest", exact_digest)
    monkeypatch.setattr(
        subprocess,
        "run",
        _completed_runner(subprocess.CompletedProcess([], 0, "1.0", "")),
    )
    monkeypatch.setattr(network_launcher, "_probe_bubblewrap", failed_probe)
    launcher, capability = network_launcher.discover_bubblewrap()
    assert launcher is None
    assert capability.evidence == ("denial",)


@pytest.mark.skipif(
    platform.system() != "Linux" or shutil.which("bwrap") is None,
    reason="real Bubblewrap evidence requires an owned Linux runner with bwrap",
)
def test_real_bubblewrap_probe_and_writable_target(tmp_path: Path) -> None:
    launcher, capability = network_launcher.discover_bubblewrap()
    assert launcher is not None, capability.evidence
    assert capability.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
    assert any(item.startswith("sha256=") for item in capability.evidence)

    tool_directory = tmp_path / "tool"
    tool_directory.mkdir()
    provider = tool_directory / "provider"
    provider.write_text(
        "#!/bin/sh\n"
        'test "$AI_STP_PROVIDER_RUNTIME_CACHE" = /tmp/ai-stp-provider-runtime\n'
        'mkdir -p "$AI_STP_PROVIDER_RUNTIME_CACHE"\n'
        'printf runtime > "$AI_STP_PROVIDER_RUNTIME_CACHE/provider-wrote"\n'
        'cat "$1" > provider-read\n'
        "printf ok > provider-wrote\n",
        encoding="utf-8",
    )
    provider.chmod(0o755)
    immutable_input = tool_directory / "bundle.zip"
    immutable_input.write_text("exact bundle", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    command = launcher.wrap(
        (str(provider.resolve()), str(immutable_input.resolve())), target=target.resolve()
    )
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)

    assert result.returncode == 0, result.stderr
    assert (target / "provider-wrote").read_text(encoding="utf-8") == "ok"
    assert (target / "provider-read").read_text(encoding="utf-8") == "exact bundle"
