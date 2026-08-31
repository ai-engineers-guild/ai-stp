"""A probed macOS ``sandbox-exec`` launcher that denies provider network access.

The executable and SBPL surface are deprecated, so their presence is never
treated as capability evidence. The consumer first proves an unprivileged
positive control can reach IPv4, IPv6 and DNS-like UDP endpoints, then requires
the same child under the profile to reach none of them. Any missing executable,
path-trust failure or probe ambiguity remains explicitly unavailable.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.provider import network_launcher
from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement
from ai_stp_foundation.canonical import JsonValue

EXECUTABLE: Final[Path] = Path("/usr/bin/sandbox-exec")
PROFILE: Final[str] = "(version 1)\n(allow default)\n(deny network*)\n"
_PROBE_TIMEOUT: Final[float] = 3.0


def _digest(path: Path) -> str:
    held = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            held.update(chunk)
    return held.hexdigest()


def _trusted_executable() -> tuple[Path | None, str | None]:
    """Return the immutable system launcher path, or the exact refusal."""
    executable = EXECUTABLE
    for candidate in (executable, *executable.parents):
        try:
            metadata = candidate.stat()
        except OSError as error:
            return None, f"cannot inspect sandbox-exec path {candidate}: {error}"
        if metadata.st_uid != 0:
            return None, f"sandbox-exec path is not root-owned: {candidate}"
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return None, f"sandbox-exec path is group/world writable: {candidate}"
        if candidate == executable:
            if not stat.S_ISREG(metadata.st_mode) or not os.access(candidate, os.X_OK):
                return None, "sandbox-exec is not an executable regular file"
        elif not stat.S_ISDIR(metadata.st_mode):
            return None, f"sandbox-exec ancestor is not a directory: {candidate}"
    return executable, None


@dataclass(frozen=True)
class SandboxExecLauncher:
    """A system ``sandbox-exec`` whose network-denial profile passed the probe."""

    executable: Path
    capability: NetworkCapability

    def __post_init__(self) -> None:
        if self.capability.enforcement is not NetworkEnforcement.ENFORCED:
            raise ValueError("a launcher requires enforced capability evidence")
        if self.capability.launcher_id != f"sandbox-exec:{self.executable.as_posix()}":
            raise ValueError("launcher identity does not match its executable")

    def wrap(self, argv: tuple[str, ...], *, target: Path) -> tuple[str, ...]:
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("provider executable must be absolute")
        if target.is_symlink() or not target.is_absolute() or not target.is_dir():
            raise ValueError("provider target must be an existing absolute directory")
        return (str(self.executable), "-p", PROFILE, *argv)

    def run(
        self,
        argv: tuple[str, ...],
        *,
        target: Path,
        writable: tuple[Path, ...] = (),
        command: str,
    ) -> JsonValue:
        """Run with network denied; filesystem access remains the provider contract's."""
        from ai_stp_cli.provider import conformance

        del writable
        return conformance.invoke_argv(self.wrap(argv, target=target), command=command)


def _probe(executable: Path) -> tuple[bool, tuple[str, ...]]:
    try:
        ipv4 = network_launcher.listener(socket.AF_INET, "127.0.0.1")
        ipv6 = network_launcher.listener(socket.AF_INET6, "::1")
        dns_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns_udp.bind(("127.0.0.1", 0))
    except OSError as error:
        for held in locals().values():
            if isinstance(held, socket.socket):
                held.close()
        return False, (f"positive-control socket unavailable: {error}",)
    try:
        network_launcher.positive_control(ipv4, ipv6, dns_udp)
        ports = {
            "ipv4": network_launcher.port(ipv4),
            "ipv6": network_launcher.port(ipv6),
            "dns_udp": network_launcher.port(dns_udp),
        }
        result = subprocess.run(
            (
                str(executable),
                "-p",
                PROFILE,
                sys.executable,
                "-c",
                network_launcher.CHILD_PROBE,
                json.dumps(ports, sort_keys=True),
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_PROBE_TIMEOUT,
            env={"PATH": os.environ.get("PATH", "")},
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            return False, (detail[-1] if detail else "sandbox-exec probe returned non-zero",)
        try:
            observed = cast(dict[str, object], json.loads(result.stdout))
        except (json.JSONDecodeError, TypeError) as error:
            return False, (f"sandbox-exec probe returned invalid JSON: {error}",)
        dns_udp.settimeout(0.5)
        try:
            packet, _peer = dns_udp.recvfrom(1024)
        except TimeoutError:
            observed["dns_udp"] = "denied"
        else:
            observed["dns_udp"] = (
                "reachable" if packet == b"ai-stp-dns-probe" else "unexpected_packet"
            )
        expected = {"dns_udp": "denied", "ipv4": "denied", "ipv6": "denied"}
        if observed != expected:
            return False, (f"network remained reachable: {observed}",)
        return True, (
            "positive control reached IPv4, IPv6 and DNS UDP endpoints",
            "sandbox-exec denied IPv4, IPv6 and DNS UDP transports",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, (f"sandbox-exec probe failed: {error}",)
    finally:
        ipv4.close()
        ipv6.close()
        dns_udp.close()


def discover_sandbox_exec() -> tuple[SandboxExecLauncher | None, NetworkCapability]:
    """Discover and prove the current host's launcher, or remain unavailable."""
    os_name = platform.system().casefold()
    if os_name != "darwin":
        return None, network_launcher.unavailable(
            os_name, "the sandbox-exec launcher is macOS-only"
        )
    executable, refusal = _trusted_executable()
    if executable is None:
        return None, network_launcher.unavailable(os_name, refusal or "sandbox-exec is absent")
    try:
        digest = _digest(executable)
    except OSError as error:
        return None, network_launcher.unavailable(os_name, f"cannot identify sandbox-exec: {error}")
    passed, evidence = _probe(executable)
    if not passed:
        return None, network_launcher.unavailable(os_name, evidence[0])
    capability = NetworkCapability(
        enforcement=NetworkEnforcement.ENFORCED,
        os_name=os_name,
        launcher_id=f"sandbox-exec:{executable.as_posix()}",
        evidence=(
            f"sha256={digest}",
            "profile allows the existing filesystem/process surface and denies network*",
            *evidence,
        ),
    )
    return SandboxExecLauncher(executable, capability), capability
