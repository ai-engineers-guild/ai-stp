"""Observed network-isolation launchers for provider protocol v2.

Linux may use Bubblewrap only after a positive-control probe proves the local
IPv4, IPv6 and DNS-like UDP endpoints are reachable outside the launcher and
the same transports are denied inside its network namespace. Absence, probe
failure or an unsupported OS is ``unavailable`` and never a weaker launch.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement

_PROBE_TIMEOUT: Final[float] = 3.0
_BWRAP_ARGUMENTS: Final[tuple[str, ...]] = (
    "--unshare-net",
    "--die-with-parent",
    "--new-session",
    "--ro-bind",
    "/",
    "/",
    "--dev",
    "/dev",
    "--proc",
    "/proc",
)
_PROVIDER_RUNTIME_CACHE: Final[str] = "/tmp/ai-stp-provider-runtime"
_CHILD_PROBE: Final[str] = """
import json, socket, sys
ports = json.loads(sys.argv[1])
results = {}
for name, family, address in (
    ("ipv4", socket.AF_INET, ("127.0.0.1", ports["ipv4"])),
    ("ipv6", socket.AF_INET6, ("::1", ports["ipv6"])),
):
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(address)
    except OSError:
        results[name] = "denied"
    else:
        results[name] = "reachable"
    finally:
        sock.close()
dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
dns.settimeout(0.5)
try:
    dns.sendto(b"ai-stp-dns-probe", ("127.0.0.1", ports["dns_udp"]))
except OSError:
    results["dns_udp"] = "send_failed"
else:
    results["dns_udp"] = "sent"
finally:
    dns.close()
print(json.dumps(results, sort_keys=True))
"""


def _path_token(path: Path) -> str:
    """Stable path text for launcher identity and argv.

    On Windows ``str(Path('/usr/bin/bwrap'))`` becomes ``\\usr\\bin\\bwrap``.
    ``as_posix()`` keeps intentional absolute POSIX paths as written.
    """
    return path.as_posix()


@dataclass(frozen=True)
class BubblewrapLauncher:
    """A Bubblewrap executable whose network namespace passed the probe."""

    executable: Path
    capability: NetworkCapability

    def __post_init__(self) -> None:
        if self.capability.enforcement is not NetworkEnforcement.ENFORCED:
            raise ValueError("a launcher requires enforced capability evidence")
        if self.capability.launcher_id != f"bubblewrap:{_path_token(self.executable)}":
            raise ValueError("launcher identity does not match its executable")

    def wrap(
        self,
        argv: tuple[str, ...],
        *,
        target: Path,
        writable: tuple[Path, ...] = (),
    ) -> tuple[str, ...]:
        """Wrap one exact local-only provider argv in the verified namespace.

        `writable` is for the paths an operation legitimately writes that are
        not the target. A setup has exactly one — the target — and binding only
        that was correct until the program lifecycle arrived with a second: the
        prefix. Left unbound, a provider writes its program into the sandbox's
        own `/tmp` tmpfs, verifies it there truthfully, and leaves nothing
        behind. Every entry is named by the caller and appears in the plan; this
        is not a general escape hatch.
        """
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("provider executable must be absolute")
        if target.is_symlink() or not target.is_absolute() or not target.is_dir():
            raise ValueError("provider target must be an existing absolute directory")
        resolved_target = target.resolve()
        readonly_files: list[str] = []
        for argument in argv:
            candidate = Path(argument)
            if candidate.is_absolute() and candidate.is_file():
                rendered = _path_token(candidate)
                if rendered not in readonly_files:
                    readonly_files.append(rendered)
        readonly_mounts = tuple(
            item for path in readonly_files for item in ("--ro-bind", path, path)
        )
        return (
            _path_token(self.executable),
            *_BWRAP_ARGUMENTS,
            "--tmpfs",
            "/tmp",
            "--chmod",
            "1777",
            "/tmp",
            "--setenv",
            "AI_STP_PROVIDER_RUNTIME_CACHE",
            _PROVIDER_RUNTIME_CACHE,
            *readonly_mounts,
            *(
                item
                for place in writable
                for item in ("--bind", _path_token(place.resolve()), _path_token(place.resolve()))
            ),
            "--bind",
            _path_token(resolved_target),
            _path_token(resolved_target),
            "--chdir",
            _path_token(resolved_target),
            "--",
            *argv,
        )


#: Why a Windows install may run a local phase with nothing denying the network.
#: Closed, because the whole point of the exception is that it is not general.
#:
#: `trusted_release` — the release was verified against the manifest, the policy
#: and its exact bytes before this was reached.
#: `explicit_unverified_provider` — the operator named an unverified provider on
#: purpose, which is already a separate, deliberate act.
TRUSTED_RELEASE: Final[str] = "trusted_release"
EXPLICIT_UNVERIFIED_PROVIDER: Final[str] = "explicit_unverified_provider"

UNISOLATED_REASONS: Final[frozenset[str]] = frozenset(
    {TRUSTED_RELEASE, EXPLICIT_UNVERIFIED_PROVIDER}
)

#: Systems where no launcher a plain CLI may use can deny the network, so the
#: exception above is the only way a local phase runs at all. Closed, and it is
#: a statement about the platform rather than about this machine.
#:
#: Linux is deliberately absent: there the absence of `bwrap` is a missing
#: dependency, not a missing capability of the operating system, and skipping a
#: capability that exists is a different act from conceding one that does not.
#:
#: macOS is here because it was missing, not because anything decided it should
#: be. `windows` was written into the name and the check, so on macOS
#: `discover_bubblewrap` returned nothing and the exception refused to be built
#: — every v3 provider call refused, on a platform whose providers we fetch and
#: attest. `sandbox-exec` may yet give macOS a real launcher; until something
#: proves one on the platform itself, it carries the same debt as Windows.
UNISOLATED_PLATFORMS: Final[frozenset[str]] = frozenset({"windows", "darwin"})


@dataclass(frozen=True)
class UnisolatedLocalPhase:
    """Permission to run one local phase with no network-denying launcher.

    A value rather than a boolean, because a boolean is something a caller
    passes without deciding. This has to be built, on the platform that needs
    it, naming which of the two reasons applies.
    """

    reason: str


def unisolated_local_phase(reason: str) -> UnisolatedLocalPhase:
    """Build the Windows exception, or refuse to.

    Windows 11 has no network-denying launcher a plain CLI may use — meaning
    none is built and proved here. `CreateProcessInSandbox` is absent on this OS
    version and Windows Sandbox is a separate optional feature. So the provider
    refused before its first spawn and nothing worked on Windows at all.

    **One half of the original reason was wrong, and it is the half that stopped
    anyone looking.** This said reaching an arbitrary target needs DACL
    traversal, so an installer would have to prepare a parent or a drive root.
    Measured on `windows-latest` (`NDDev-OpenNetwork/claude-setup-system`, run
    33302576898): an AppContainer read a target carrying **only its own ACE**,
    with no ACE anywhere on the parent — bypass-traverse is granted broadly by
    default. The probe enumerated the parent's DACL for that SID and printed
    nothing, so the control fired rather than being assumed.

    That does not lift the debt: a launcher still has to exist and be proved on
    the platform, and an unproved one is a green guard over nothing. It does
    remove the reason recorded for why one could not be built, which is why the
    sentence is corrected here rather than left as harmless history.

    This is deliberate security debt, scoped by `#416`: a provider the operator
    chose can technically use the network during a local phase. It is not a
    claim to isolation — `provider network` keeps reporting `unavailable`,
    because reporting `enforced` would hide the debt in the one output someone
    would check for it.

    It cannot be built anywhere else. On Linux an unisolated phase is not a
    concession to a missing capability, it is a proved capability being skipped,
    and those are different things that must not share a code path.
    """
    os_name = platform.system().lower()
    if os_name not in UNISOLATED_PLATFORMS:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this system can deny the network, so a local phase is not excused from it",
            details={"os": os_name, "reason": reason},
            next_actions=["provider network --json"],
        )
    if reason not in UNISOLATED_REASONS:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that is not a reason a local phase may run without network isolation",
            details={"reason": reason, "allowed": ", ".join(sorted(UNISOLATED_REASONS))},
        )
    return UnisolatedLocalPhase(reason=reason)


def _unavailable(os_name: str, reason: str) -> NetworkCapability:
    return NetworkCapability(
        enforcement=NetworkEnforcement.UNAVAILABLE,
        os_name=os_name,
        launcher_id=None,
        evidence=(reason,),
    )


def _digest(path: Path) -> str:
    held = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            held.update(chunk)
    return held.hexdigest()


def _system_path_refusal(executable: Path) -> str | None:
    """Require a launcher path the invoking user cannot replace or rewrite."""
    for candidate in (executable, *executable.parents):
        try:
            metadata = candidate.stat()
        except OSError as error:
            return f"cannot inspect bwrap path {candidate}: {error}"
        if metadata.st_uid != 0:
            return f"bwrap path is not root-owned: {candidate}"
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return f"bwrap path is group/world writable: {candidate}"
        if candidate == executable:
            # `os.access(X_OK)` rather than `paths.is_executable_file`, and the
            # difference is the point: this is the only executable check in the
            # CLI that is Linux-only by construction. `bwrap` exists nowhere
            # else, `UNISOLATED_PLATFORMS` concedes Windows and macOS above, and
            # the root-ownership test two lines up is already a POSIX question.
            # The portable predicate would be a weaker answer here, not a safer
            # one — it asks about a name where this asks about a permission.
            if not stat.S_ISREG(metadata.st_mode) or not os.access(candidate, os.X_OK):
                return "bwrap is not an executable regular file"
        elif not stat.S_ISDIR(metadata.st_mode):
            return f"bwrap ancestor is not a directory: {candidate}"
    return None


def _listener(family: socket.AddressFamily, address: str) -> socket.socket:
    listener = socket.socket(family, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((address, 0))
    listener.listen(2)
    listener.settimeout(_PROBE_TIMEOUT)
    return listener


def _port(sock: socket.socket) -> int:
    address = sock.getsockname()
    if not isinstance(address, tuple) or not isinstance(address[1], int):
        raise OSError("probe socket has no numeric port")
    return address[1]


def _positive_control(ipv4: socket.socket, ipv6: socket.socket, dns_udp: socket.socket) -> None:
    for family, address, listener in (
        (socket.AF_INET, "127.0.0.1", ipv4),
        (socket.AF_INET6, "::1", ipv6),
    ):
        with socket.socket(family, socket.SOCK_STREAM) as client:
            client.settimeout(_PROBE_TIMEOUT)
            client.connect((address, _port(listener)))
        accepted, _peer = listener.accept()
        accepted.close()
    token = b"ai-stp-dns-probe"
    dns_udp.settimeout(_PROBE_TIMEOUT)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.sendto(token, ("127.0.0.1", _port(dns_udp)))
    observed, _peer = dns_udp.recvfrom(len(token) + 1)
    if observed != token:
        raise OSError("DNS transport positive control returned unexpected bytes")


def _probe_bubblewrap(executable: Path) -> tuple[bool, tuple[str, ...]]:
    try:
        ipv4 = _listener(socket.AF_INET, "127.0.0.1")
        ipv6 = _listener(socket.AF_INET6, "::1")
        dns_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns_udp.bind(("127.0.0.1", 0))
    except OSError as error:
        for held in locals().values():
            if isinstance(held, socket.socket):
                held.close()
        return False, (f"positive-control socket unavailable: {error}",)
    try:
        _positive_control(ipv4, ipv6, dns_udp)
        ports = {"ipv4": _port(ipv4), "ipv6": _port(ipv6), "dns_udp": _port(dns_udp)}
        result = subprocess.run(
            (
                str(executable),
                *_BWRAP_ARGUMENTS,
                "--",
                sys.executable,
                "-c",
                _CHILD_PROBE,
                json.dumps(ports, sort_keys=True),
            ),
            check=False,
            capture_output=True,
            text=True,
            # Decode by the contract, not by the ambient locale.
            encoding="utf-8",
            timeout=_PROBE_TIMEOUT,
            env={"PATH": os.environ.get("PATH", "")},
        )
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            return False, (detail[-1] if detail else "bubblewrap probe returned non-zero",)
        try:
            observed = cast(dict[str, object], json.loads(result.stdout))
        except (json.JSONDecodeError, TypeError) as error:
            return False, (f"bubblewrap probe returned invalid JSON: {error}",)
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
            "network namespace denied IPv4, IPv6 and DNS UDP transports",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, (f"bubblewrap probe failed: {error}",)
    finally:
        ipv4.close()
        ipv6.close()
        dns_udp.close()


def discover_bubblewrap() -> tuple[BubblewrapLauncher | None, NetworkCapability]:
    """Discover and prove the Linux Bubblewrap launcher, or fail closed."""
    os_name = platform.system().lower()
    if os_name != "linux":
        return None, _unavailable(os_name, "Bubblewrap launcher is Linux-only")
    found = shutil.which("bwrap")
    if found is None:
        return None, _unavailable(os_name, "bwrap executable is absent")
    executable = Path(found).resolve()
    refusal = _system_path_refusal(executable)
    if refusal is not None:
        return None, _unavailable(os_name, refusal)
    try:
        version = subprocess.run(
            (str(executable), "--version"),
            check=True,
            capture_output=True,
            text=True,
            # Decode by the contract, not by the ambient locale.
            encoding="utf-8",
            timeout=_PROBE_TIMEOUT,
        ).stdout.strip()
        digest = _digest(executable)
    except (OSError, subprocess.SubprocessError) as error:
        return None, _unavailable(os_name, f"cannot identify bwrap: {error}")
    passed, probe_evidence = _probe_bubblewrap(executable)
    if not passed:
        return None, _unavailable(os_name, probe_evidence[0])
    capability = NetworkCapability(
        enforcement=NetworkEnforcement.ENFORCED,
        os_name=os_name,
        launcher_id=f"bubblewrap:{_path_token(executable)}",
        evidence=(f"version={version}", f"sha256={digest}", *probe_evidence),
    )
    return BubblewrapLauncher(executable, capability), capability
