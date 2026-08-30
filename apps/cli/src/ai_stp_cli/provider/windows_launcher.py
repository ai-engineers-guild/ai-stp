# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
#
# Four names cause every one of these: `ctypes.WinDLL`, `ctypes.get_last_error`,
# `ctypes.wintypes` and `msvcrt.open_osfhandle` do not exist in the stubs for a
# type checker running on Linux, which is where `back-static` runs.
#
# What that costs, said plainly rather than left implicit: the Windows half of
# this module is type-checked nowhere. The suppression is not hiding a diagnosis
# that would appear elsewhere — there is no elsewhere. So the cover has to come
# from the tests, and it does: the discovery path is exercised on every platform
# and the isolated spawn is exercised on `windows-latest`, where a wrong
# argument type is a failed `CreateProcessW` rather than a silent success.
#
# Every entry point is guarded at runtime by `_windows()`, so importing this on
# Linux is safe and calling into it there fails closed.
"""The Windows network-denying launcher, and the probe that proves it.

`ADR-0126` recorded a debt: Linux denies the network for a local provider phase
through Bubblewrap and Windows denied nothing, so the phase ran unisolated
under a trust exception. `#51` asks for a native launcher and names
AppContainer, with one objection — that it cannot reach an arbitrary target
without editing the parents' DACLs.

`ADR-0131` measured that objection and it is false: bypass traverse checking
survives into an AppContainer token, so a leaf carrying an ACE for the package
SID is reachable by full path while its parents carry none. The cost is one ACE
on the target and one on the runtime, and nothing above them.

What the same measurement established about the network, on `windows-latest`:
TCP to the parent's loopback listeners is denied on both families, a grandchild
spawned inside inherits the denial, and a UDP datagram sent from inside never
arrives. The denial is enforced by WFP on `FWPM_CONDITION_ALE_PACKAGE_ID` —
by the device rather than by agreement, which is what `#51` requires.

Two limits are carried deliberately rather than assumed away, both from
`ADR-0131`. The runner that measured this was elevated, so nothing here proves
a non-elevated user can create a profile — the code fails closed if it cannot.
And an AppContainer's denial appears as a *timeout* rather than the immediate
refusal Linux gives, because the block sits at the accept layer; a timeout is
compatible with a slow listener, so it is the positive control that makes it
evidence, and no capability is reported enforced without one.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Final, Self, cast

from ai_stp_cli.provider.network_launcher import (
    CHILD_PROBE,
    listener,
    port,
    positive_control,
    unavailable,
)
from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement
from ai_stp_foundation.canonical import JsonValue

#: The AppContainer moniker this program creates. Stable, because the package
#: SID is derived from it and a changing name would strand the ACEs granted
#: under the previous one.
PROFILE_NAME: Final[str] = "ai-stp-provider-local-phase"

#: `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`, which is
#: `ProcThreadAttributeSecurityCapabilities` (9) or'd with
#: `PROC_THREAD_ATTRIBUTE_INPUT` (0x00020000).
_ATTRIBUTE_SECURITY_CAPABILITIES: Final[int] = 0x00020009

_EXTENDED_STARTUPINFO_PRESENT: Final[int] = 0x00080000
_CREATE_NO_WINDOW: Final[int] = 0x08000000
_STARTF_USESTDHANDLES: Final[int] = 0x00000100
_HANDLE_FLAG_INHERIT: Final[int] = 0x00000001
_ERROR_ALREADY_EXISTS: Final[int] = 0xB7

_PROBE_TIMEOUT: Final[float] = 20.0


def _windows() -> bool:
    return platform.system().casefold() == "windows"


class _SecurityCapabilities(ctypes.Structure):
    _fields_ = (
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", ctypes.c_uint32),
        ("Reserved", ctypes.c_uint32),
    )


class _SecurityAttributes(ctypes.Structure):
    _fields_ = (
        ("nLength", ctypes.c_uint32),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", ctypes.c_int32),
    )


class _ProcessInformation(ctypes.Structure):
    _fields_ = (
        ("hProcess", ctypes.c_void_p),
        ("hThread", ctypes.c_void_p),
        ("dwProcessId", ctypes.c_uint32),
        ("dwThreadId", ctypes.c_uint32),
    )


class _StartupInfoEx(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_uint32),
        ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p),
        ("dwX", ctypes.c_uint32),
        ("dwY", ctypes.c_uint32),
        ("dwXSize", ctypes.c_uint32),
        ("dwYSize", ctypes.c_uint32),
        ("dwXCountChars", ctypes.c_uint32),
        ("dwYCountChars", ctypes.c_uint32),
        ("dwFillAttribute", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("wShowWindow", ctypes.c_uint16),
        ("cbReserved2", ctypes.c_uint16),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p),
        ("hStdError", ctypes.c_void_p),
        ("lpAttributeList", ctypes.c_void_p),
    )


@dataclass(frozen=True)
class _Api:
    """The three libraries this needs, loaded once and only on Windows."""

    kernel: Any
    userenv: Any
    advapi: Any

    @classmethod
    def load(cls) -> Self:
        return cls(
            kernel=ctypes.WinDLL("kernel32", use_last_error=True),
            userenv=ctypes.WinDLL("userenv", use_last_error=True),
            advapi=ctypes.WinDLL("advapi32", use_last_error=True),
        )


class AppContainerProcess:
    """A process inside an AppContainer, shaped like `subprocess.Popen`.

    Only the four members the provider boundary uses: `stdout`, `kill`, `wait`
    and the context manager. It exists because `subprocess` cannot create an
    AppContainer — `STARTUPINFO.lpAttributeList` accepts only a handle list —
    while `conformance._bounded_output` owns the read limit, the watchdog and
    the environment allowlist, and none of that should be written twice.

    Output arrives on an inherited pipe rather than through a file. A handle is
    already open when the child receives it, so nothing is resolved and no ACL
    is consulted on the child's side; a container that cannot reach a path can
    still say so. Three earlier attempts collected the answer from disk and
    reported silence with two explanations and no way to tell them apart.
    """

    def __init__(self, api: _Api, sid: ctypes.c_void_p, argv: list[str], env: dict[str, str]):
        self._api = api
        self._handle: ctypes.c_void_p | None = None
        self.stdout: IO[bytes] | None = None
        attributes = _SecurityAttributes(
            nLength=ctypes.sizeof(_SecurityAttributes), lpSecurityDescriptor=None, bInheritHandle=1
        )
        read_end, write_end = ctypes.c_void_p(), ctypes.c_void_p()
        if not api.kernel.CreatePipe(
            ctypes.byref(read_end), ctypes.byref(write_end), ctypes.byref(attributes), 0
        ):
            raise OSError(ctypes.get_last_error(), "the isolation pipe could not be created")
        # The read end must not travel to the child, or this process never sees
        # end of file: its own copy keeps the pipe open after the child exits.
        api.kernel.SetHandleInformation(read_end, _HANDLE_FLAG_INHERIT, 0)

        size = ctypes.c_size_t(0)
        api.kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        self._attributes = ctypes.create_string_buffer(size.value)
        capabilities = _SecurityCapabilities(
            AppContainerSid=sid, Capabilities=None, CapabilityCount=0, Reserved=0
        )
        started = bool(
            api.kernel.InitializeProcThreadAttributeList(self._attributes, 1, 0, ctypes.byref(size))
        ) and bool(
            api.kernel.UpdateProcThreadAttribute(
                self._attributes,
                0,
                ctypes.c_size_t(_ATTRIBUTE_SECURITY_CAPABILITIES),
                ctypes.byref(capabilities),
                ctypes.sizeof(capabilities),
                None,
                None,
            )
        )
        if not started:
            api.kernel.CloseHandle(read_end)
            api.kernel.CloseHandle(write_end)
            raise OSError(ctypes.get_last_error(), "the isolation attributes were refused")

        start = _StartupInfoEx()
        start.cb = ctypes.sizeof(_StartupInfoEx)
        start.dwFlags = _STARTF_USESTDHANDLES
        start.hStdOutput = write_end
        start.hStdError = write_end
        start.hStdInput = None
        start.lpAttributeList = ctypes.cast(self._attributes, ctypes.c_void_p)
        information = _ProcessInformation()
        block = "\0".join(f"{name}={value}" for name, value in sorted(env.items())) + "\0\0"
        created = api.kernel.CreateProcessW(
            None,
            ctypes.create_unicode_buffer(subprocess.list2cmdline(argv)),
            None,
            None,
            True,
            _EXTENDED_STARTUPINFO_PRESENT | _CREATE_NO_WINDOW | 0x00000400,
            ctypes.create_unicode_buffer(block),
            None,
            ctypes.byref(start),
            ctypes.byref(information),
        )
        api.kernel.CloseHandle(write_end)
        if not created:
            api.kernel.CloseHandle(read_end)
            raise OSError(ctypes.get_last_error(), "the provider could not be started isolated")
        api.kernel.CloseHandle(information.hThread)
        self._handle = ctypes.c_void_p(information.hProcess)
        self.stdout = cast(
            "IO[bytes]", os.fdopen(msvcrt_open_osfhandle(read_end.value or 0), "rb", 0)
        )

    def kill(self) -> None:
        if self._handle is not None:
            self._api.kernel.TerminateProcess(self._handle, 1)

    def wait(self) -> int:
        if self._handle is None:
            return 0
        self._api.kernel.WaitForSingleObject(self._handle, 0xFFFFFFFF)
        code = ctypes.c_uint32()
        self._api.kernel.GetExitCodeProcess(self._handle, ctypes.byref(code))
        return int(code.value)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        if self.stdout is not None:
            self.stdout.close()
        if self._handle is not None:
            self._api.kernel.CloseHandle(self._handle)
            self._handle = None


def msvcrt_open_osfhandle(handle: int) -> int:
    """`msvcrt.open_osfhandle`, imported where a type checker on Linux tolerates it."""
    import msvcrt

    return msvcrt.open_osfhandle(handle, os.O_RDONLY)


def _profile(api: _Api) -> tuple[ctypes.c_void_p, str]:
    """Create or re-derive the AppContainer profile and return its package SID.

    An existing profile is derived rather than recreated: the SID is a function
    of the moniker, and ACEs already granted under it stay valid. Any other
    failure is a failure — a launcher that cannot name its own principal cannot
    grant anything to it, and reporting enforced from there would be a claim
    with no subject.
    """
    sid = ctypes.c_void_p()
    api.userenv.CreateAppContainerProfile.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.userenv.CreateAppContainerProfile.restype = ctypes.c_long
    result = api.userenv.CreateAppContainerProfile(
        PROFILE_NAME,
        PROFILE_NAME,
        "ai_stp provider local phase, denied the network",
        None,
        0,
        ctypes.byref(sid),
    )
    if result < 0 and (result & 0xFFFF) == _ERROR_ALREADY_EXISTS:
        api.userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        api.userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
        result = api.userenv.DeriveAppContainerSidFromAppContainerName(
            PROFILE_NAME, ctypes.byref(sid)
        )
    if result < 0:
        raise OSError(result, "no AppContainer profile could be created or derived")

    text = ctypes.c_wchar_p()
    api.advapi.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    api.advapi.ConvertSidToStringSidW.restype = ctypes.c_int32
    if not api.advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)) or not text.value:
        raise OSError(ctypes.get_last_error(), "the package SID could not be rendered")
    rendered = text.value
    api.kernel.LocalFree(text)
    return sid, rendered


def _icacls(package: str, target: Path, rights: str, *, inherit: bool) -> bool:
    """Grant the package SID one right on one path, and say whether it took.

    `inherit` is the difference between granting a directory and granting
    everything beneath it. It matters more than it looks: an `(OI)(CI)` grant on
    an ancestor reaches every descendant, which is how a measurement of this
    very mechanism once granted the tree it was using as its negative control.
    """
    scope = "(OI)(CI)" if inherit else ""
    done = subprocess.run(
        ["icacls", str(target), "/grant", f"*{package}:{scope}{rights}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=_PROBE_TIMEOUT,
    )
    return done.returncode == 0


def _revoke(package: str, target: Path) -> None:
    """Take the grant back. Best effort, because leaving it is not a failure.

    An ACE that outlives its operation widens what the next isolated phase can
    reach, so it is removed. But a revoke that fails must not turn a completed
    provider call into an error: the effect has landed, and the caller learning
    about a cleanup problem as an operation failure is worse than the ACE.
    """
    subprocess.run(
        ["icacls", str(target), "/remove:g", f"*{package}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=_PROBE_TIMEOUT,
    )


@dataclass(frozen=True)
class AppContainerLauncher:
    """An AppContainer profile whose network denial passed the probe."""

    package_sid: str
    capability: NetworkCapability

    def __post_init__(self) -> None:
        if self.capability.enforcement is not NetworkEnforcement.ENFORCED:
            raise ValueError("a launcher requires enforced capability evidence")
        if self.capability.launcher_id != f"appcontainer:{self.package_sid}":
            raise ValueError("launcher identity does not match its package SID")

    def run(
        self,
        argv: tuple[str, ...],
        *,
        target: Path,
        writable: tuple[Path, ...] = (),
        command: str,
    ) -> JsonValue:
        """Grant, run isolated under the ordinary boundary, then take it back.

        The grants are the whole of the isolation's file side and they are the
        two `#51` allows: the target and the executable's own directory, plus
        whatever the caller named writable. Every ancestor of all of them is
        left alone, which `ADR-0131` measured to be enough — bypass traverse
        checking survives into the token, so a full path reaches a granted leaf
        through ungranted parents.

        The read limit, the watchdog and the environment allowlist are not
        reimplemented here. `conformance.invoke_argv` owns them and takes the
        process factory instead, so the Windows path cannot drift from the one
        that already learned what an unbounded read costs.

        Revoked in `finally`, on success and on failure alike: an ACE that
        outlives its operation widens what the next isolated phase can reach.
        """
        from ai_stp_cli.provider import conformance

        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("provider executable must be absolute")
        if target.is_symlink() or not target.is_absolute() or not target.is_dir():
            raise ValueError("provider target must be an existing absolute directory")
        api = _Api.load()
        sid, package = _profile(api)
        if package != self.package_sid:
            raise ValueError("the derived package SID is not the one this launcher proved")

        runtime = Path(argv[0]).resolve().parent
        wanted: tuple[tuple[Path, str], ...] = (
            (target.resolve(), "(M)"),
            *((Path(item).resolve(), "(M)") for item in writable),
            (runtime, "(RX)"),
        )
        granted: list[Path] = []
        try:
            for path, rights in wanted:
                if not _icacls(package, path, rights, inherit=True):
                    raise OSError(f"the container could not be granted {path}")
                granted.append(path)

            def factory(command_argv: list[str], environment: dict[str, str]) -> Any:
                return AppContainerProcess(api, sid, command_argv, environment)

            return conformance.invoke_argv(argv, command=command, spawn=factory)
        finally:
            for path in granted:
                _revoke(package, path)


def _probe(api: _Api, sid: ctypes.c_void_p, package: str) -> tuple[bool, tuple[str, ...]]:
    """Prove the denial the same way Linux does, or refuse to claim it.

    Same shape and the same child text: loopback listeners, a positive control
    proving this process reaches them, then the identical connect from inside.
    `#51` requires the claim to rest on the same class of probe, and sharing the
    literal is the only version of that which cannot drift.

    The control carries more weight here than it does on Linux. A namespace
    refuses immediately; an AppContainer's block sits at the accept layer and
    the caller sees a timeout, which is also what a slow listener looks like.
    The control is what separates them, so a control that did not pass makes the
    whole reading unavailable rather than enforced.
    """
    try:
        ipv4 = listener(socket.AF_INET, "127.0.0.1")
        ipv6 = listener(socket.AF_INET6, "::1")
        dns_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns_udp.bind(("127.0.0.1", 0))
    except OSError as error:
        return False, (f"positive-control socket unavailable: {error}",)

    home = Path(os.environ.get("TEMP", ".")) / f"{PROFILE_NAME}-probe"
    try:
        positive_control(ipv4, ipv6, dns_udp)
        ports = {"ipv4": port(ipv4), "ipv6": port(ipv6), "dns_udp": port(dns_udp)}
        home.mkdir(parents=True, exist_ok=True)
        script = home / "probe.py"
        script.write_text(CHILD_PROBE, encoding="utf-8")
        runtime = Path(sys.executable).resolve().parent
        if not _icacls(package, home, "(M)", inherit=True) or not _icacls(
            package, runtime, "(RX)", inherit=True
        ):
            return False, ("the container could not be granted its probe and runtime",)
        argv = [sys.executable, str(script), json.dumps(ports, sort_keys=True)]
        with AppContainerProcess(api, sid, argv, {"PATH": os.environ.get("PATH", "")}) as child:
            stream = child.stdout
            raw = stream.read() if stream is not None else b""
            child.wait()
        try:
            observed = cast(dict[str, object], json.loads(raw.decode("utf-8").strip()))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            return False, (f"the isolated probe returned no usable answer: {error}",)

        # Arrival decides the datagram, never the sender's return value:
        # `sendto` succeeds on a datagram the filter drops, so the child saying
        # "sent" is a statement about the call and not about the network.
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
            "the AppContainer denied IPv4, IPv6 and DNS UDP transports",
            f"package SID {package}",
        )
    except (OSError, ValueError) as error:
        return False, (f"the AppContainer probe failed: {error}",)
    finally:
        ipv4.close()
        ipv6.close()
        dns_udp.close()
        _revoke(package, home)
        _revoke(package, Path(sys.executable).resolve().parent)


def discover_appcontainer() -> tuple[AppContainerLauncher | None, NetworkCapability]:
    """Discover and prove the Windows AppContainer launcher, or fail closed.

    Every path out of here that is not a passed probe is `unavailable`. That is
    not caution for its own sake: `provider network` reporting enforced is the
    one output somebody checks before trusting a local phase, and an enforced
    claim from an unproved launcher hides the debt in the place it would be
    looked for.
    """
    os_name = platform.system().casefold()
    if not _windows():
        return None, unavailable(os_name, "the AppContainer launcher is Windows-only")
    try:
        api = _Api.load()
        sid, package = _profile(api)
    except OSError as error:
        return None, unavailable(os_name, f"no AppContainer profile: {error}")

    passed, evidence = _probe(api, sid, package)
    if not passed:
        return None, unavailable(os_name, evidence[0])
    capability = NetworkCapability(
        enforcement=NetworkEnforcement.ENFORCED,
        os_name=os_name,
        launcher_id=f"appcontainer:{package}",
        evidence=evidence,
    )
    return AppContainerLauncher(package_sid=package, capability=capability), capability
