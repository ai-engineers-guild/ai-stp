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
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.provider import network_launcher
from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement
from ai_stp_foundation.canonical import JsonValue

EXECUTABLE: Final[Path] = Path("/usr/bin/sandbox-exec")

#: The profile the probe runs under, and the one a provider gets when nothing is
#: writable. Network denied; every write denied after it.
#:
#: `(allow default)` first and narrowing after is deliberate, and it is not the
#: same as leaving the default open. SBPL takes the **last** matching rule, so
#: `(deny file-write*)` following it makes writing denied by default while
#: leaving reads, `mach`, `sysctl` and process behaviour as they were. A full
#: `(deny default)` would need every one of those enumerated for seven different
#: providers, each of which loads its own runtime — a rule set that could only be
#: completed by discovering what it broke.
#:
#: What this closes: `run` used to `del writable` and hand the provider this
#: profile with nothing after `(deny network*)`, so a local phase could write
#: anywhere the invoking user could. Linux binds the target and the named
#: writable paths and mounts the rest read-only; Windows grants exactly those two
#: places. macOS said `writable` and meant nothing by it, and a contract that
#: means one thing on two systems and nothing on the third is not a contract.
PROFILE: Final[str] = "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"

#: Character devices a program is entitled to write to whatever else it may not.
#: Denying these breaks writing to a closed pipe, seeding a random generator and
#: opening a terminal — none of which is filesystem access in the sense the
#: writable contract is about.
_DEVICE_WRITES: Final[tuple[str, ...]] = (
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/dtracehelper",
    "/dev/tty",
)

_PROBE_TIMEOUT: Final[float] = 3.0

#: The write half of the profile, probed the way the network half is. The same
#: child writes under `inside`, the one subtree the profile reopens, and under
#: `outside`, its sibling; the positive control runs it with no profile at all.
WRITE_PROBE: Final[str] = """
import json, pathlib, sys
results = {}
for name in ("inside", "outside"):
    place = pathlib.Path(sys.argv[1]) / name / "probe"
    try:
        place.write_text("ai-stp-write-probe", encoding="utf-8")
    except OSError:
        results[name] = "denied"
    else:
        results[name] = "written"
print(json.dumps(results, sort_keys=True))
"""


def _forbidden(rendered: str) -> bool:
    """Whether this spelling could end the SBPL literal it would sit inside."""
    return '"' in rendered or "\\" in rendered


def _quote(path: Path) -> str:
    """One SBPL string literal. Refuses rather than escapes.

    A path containing a quote or a backslash would end the literal early and the
    rest would be read as policy — the one way a profile can be widened by a
    filename. No such path can be a provider target here, so refusing is both
    safe and free.

    The given spelling is judged before `resolve` is called, not after. Refusing
    the input is the rule; whether the filesystem can resolve such a name is a
    separate question with a different answer on each platform, and a check that
    reached the answer through `resolve` would be relying on the very system
    call that a hostile name is most likely to break.
    """
    if _forbidden(path.as_posix()):
        raise ValueError(f"a sandbox path may not contain a quote or a backslash: {path}")
    rendered = path.resolve().as_posix()
    if _forbidden(rendered):
        raise ValueError(f"a sandbox path may not contain a quote or a backslash: {rendered}")
    return f'"{rendered}"'


def profile_for(target: Path, writable: tuple[Path, ...]) -> str:
    """The profile for one invocation: network denied, writes only where named.

    The order is the policy. `(deny file-write*)` closes writing, and every
    `(allow file-write* ...)` after it reopens exactly one subtree — the target,
    each path the caller named writable, and the character devices above.
    """
    places = (target, *writable)
    allowed = " ".join(f"(subpath {_quote(place)})" for place in places)
    devices = " ".join(f'(literal "{name}")' for name in _DEVICE_WRITES)
    return f"{PROFILE}(allow file-write* {allowed} {devices})\n"


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

    def wrap(
        self, argv: tuple[str, ...], *, target: Path, writable: tuple[Path, ...] = ()
    ) -> tuple[str, ...]:
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("provider executable must be absolute")
        if target.is_symlink() or not target.is_absolute() or not target.is_dir():
            raise ValueError("provider target must be an existing absolute directory")
        return (self.executable.as_posix(), "-p", profile_for(target, writable), *argv)

    def run(
        self,
        argv: tuple[str, ...],
        *,
        target: Path,
        writable: tuple[Path, ...] = (),
        command: str,
    ) -> JsonValue:
        """Run with the network denied and writes bounded by target and `writable`."""
        from ai_stp_cli.provider import conformance

        return conformance.invoke_argv(
            self.wrap(argv, target=target, writable=writable), command=command
        )


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
                executable.as_posix(),
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


def _answer(argv: tuple[str, ...]) -> dict[str, object]:
    """Run one probe child and read its one-line JSON answer, or refuse."""
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_PROBE_TIMEOUT,
        env={"PATH": os.environ.get("PATH", "")},
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        raise ValueError(detail[-1] if detail else "probe child returned non-zero")
    try:
        return cast(dict[str, object], json.loads(result.stdout))
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f"probe child returned invalid JSON: {error}") from error


def _write_probe(executable: Path) -> tuple[bool, tuple[str, ...]]:
    """Prove the profile bounds writes, or refuse to claim it.

    `discover_sandbox_exec` used to say "every write outside the target is
    denied" on the strength of the network probe alone: the sentence was in
    the evidence and nothing had measured it. Same shape as `_probe` — a
    positive control first, then the identical child under the profile — and
    the same rule: a control that did not pass makes the reading unavailable.
    """
    root = Path(tempfile.mkdtemp(prefix="ai-stp-sandbox-write-"))
    inside, outside = root / "inside", root / "outside"
    try:
        inside.mkdir()
        outside.mkdir()
        child = (sys.executable, "-c", WRITE_PROBE, root.resolve().as_posix())
        control = _answer(child)
        if control != {"inside": "written", "outside": "written"}:
            return False, (f"write positive control failed: {control}",)
        for place in (inside, outside):
            (place / "probe").unlink(missing_ok=True)
        observed = _answer((executable.as_posix(), "-p", profile_for(inside, ()), *child))
        if observed != {"inside": "written", "outside": "denied"}:
            return False, (f"writes were not bounded by the profile: {observed}",)
        return True, (
            "positive control wrote inside and outside the target",
            "sandbox-exec allowed the write inside the target and denied the one outside",
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return False, (f"sandbox-exec write probe failed: {error}",)
    finally:
        shutil.rmtree(root, ignore_errors=True)


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
    bounded, writes = _write_probe(executable)
    if not bounded:
        return None, network_launcher.unavailable(os_name, writes[0])
    capability = NetworkCapability(
        enforcement=NetworkEnforcement.ENFORCED,
        os_name=os_name,
        launcher_id=f"sandbox-exec:{executable.as_posix()}",
        evidence=(
            f"sha256={digest}",
            "profile denies network* and every write outside the target and "
            "the paths the caller named writable",
            *evidence,
            *writes,
        ),
    )
    return SandboxExecLauncher(executable, capability), capability
