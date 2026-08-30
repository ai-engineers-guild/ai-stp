# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
#
# Every suppression above is one name: `ctypes.WinDLL`, `ctypes.get_last_error`
# and `ctypes.wintypes` do not exist for a type checker running on Linux, and
# this file is guarded at runtime by `platform.system()`. Suppressing at the
# file rather than the line because the alternative is thirty identical
# comments saying the same thing.
#
# Learned the expensive way: this script broke `back-static` and six commits
# went out behind it, because a probe felt like a measurement rather than
# repository code. It is repository code and the gate covers it.
"""Measure what a Windows AppContainer actually enforces, on Windows.

Not a design and not a launcher: the questions below decide whether a native
Windows isolated transport is possible at all, and every one of them is a fact
about the running system rather than about the documentation. `#51` names
AppContainer as a candidate and says it "does not reach an arbitrary target
without editing the parents' DACLs" — that claim is what question 5 tests.

Run on `windows-latest`; on anything else it says so and exits clean.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

CHILD = r"""
import json, socket, sys
from pathlib import Path
ports = json.loads(sys.argv[1])
grant, deny = sys.argv[2], sys.argv[3]
out = {}
for name, family, address in (
    ("ipv4", socket.AF_INET, ("127.0.0.1", ports["ipv4"])),
    ("ipv6", socket.AF_INET6, ("::1", ports["ipv6"])),
):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        s.connect(address)
    except OSError as exc:
        out[name] = "denied:" + type(exc).__name__
    else:
        out[name] = "reachable"
    finally:
        s.close()
d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
d.settimeout(1.5)
try:
    d.sendto(b"probe", ("127.0.0.1", ports["dns_udp"]))
except OSError as exc:
    out["dns_udp"] = "denied:" + type(exc).__name__
else:
    out["dns_udp"] = "sent"
finally:
    d.close()
for label, target in (("leaf_only", grant), ("ungranted", deny), ("full_chain", sys.argv[4])):
    try:
        out[label] = sorted(p.name for p in Path(target).iterdir())[:3] or ["<empty>"]
    except OSError as exc:
        out[label] = "denied:" + type(exc).__name__ + ":" + str(getattr(exc, "winerror", ""))
sub = None
try:
    sub = subprocess.run(
        [sys.executable, "-c",
         "import socket,sys;s=socket.socket();s.settimeout(1.5);\n"
         "try:\n s.connect(('127.0.0.1',%d));print('reachable')\n"
         "except OSError as e:\n print('denied:'+type(e).__name__)" % ports["ipv4"]],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    ).stdout.strip()
except Exception as exc:
    sub = "child_spawn_failed:" + type(exc).__name__
out["grandchild"] = sub
print(json.dumps(out, sort_keys=True))
"""


def _listener(family: socket.AddressFamily, address: str) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.bind((address, 0))
    sock.listen(1)
    return sock


def main() -> int:
    report: dict[str, Any] = {"platform": platform.system(), "release": platform.release()}
    if platform.system().casefold() != "windows":
        report["skipped"] = "this probe measures Windows and must run there"
        print(json.dumps(report, indent=1, sort_keys=True))
        return 0

    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    # 1. Is the process elevated? A launcher a consumer can use must not need it.
    try:
        report["is_admin"] = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as exc:
        report["is_admin"] = f"unknown:{type(exc).__name__}"

    # 2. Can a profile be created without elevation?
    name = "ai-stp-isolation-probe"
    sid = ctypes.c_void_p()
    userenv.CreateAppContainerProfile.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    hr = userenv.CreateAppContainerProfile(
        name, name, "ai_stp network isolation probe", None, 0, ctypes.byref(sid)
    )
    report["create_profile_hresult"] = hex(hr & 0xFFFFFFFF)
    if hr < 0 and (hr & 0xFFFF) == 0xB7:  # ERROR_ALREADY_EXISTS
        userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
        hr = userenv.DeriveAppContainerSidFromAppContainerName(name, ctypes.byref(sid))
        report["derive_hresult"] = hex(hr & 0xFFFFFFFF)
    if hr < 0:
        report["verdict"] = "no AppContainer profile; a native launcher cannot be built this way"
        print(json.dumps(report, indent=1, sort_keys=True))
        return 0

    text = wintypes.LPWSTR()
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    if advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        report["package_sid"] = text.value
        kernel.LocalFree(text)

    # 3/4/5. Loopback listeners with a positive control, then the child.
    ipv4, ipv6 = _listener(socket.AF_INET, "127.0.0.1"), _listener(socket.AF_INET6, "::1")
    dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns.bind(("127.0.0.1", 0))
    ports = {
        "ipv4": ipv4.getsockname()[1],
        "ipv6": ipv6.getsockname()[1],
        "dns_udp": dns.getsockname()[1],
    }
    report["ports"] = ports

    control: dict[str, str] = {}
    for label, family, address in (
        ("ipv4", socket.AF_INET, "127.0.0.1"),
        ("ipv6", socket.AF_INET6, "::1"),
    ):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as client:
                client.settimeout(3.0)
                client.connect((address, ports[label]))
            accepted, _ = (ipv4 if label == "ipv4" else ipv6).accept()
            accepted.close()
            control[label] = "reachable"
        except OSError as exc:
            control[label] = f"unreachable:{type(exc).__name__}"
    report["positive_control_from_parent"] = control

    # A shallow root the parent controls, so the ancestor chain is short and
    # explicit rather than buried under a user profile.
    root = Path(os.environ.get("SYSTEMDRIVE", "C:") + "\\ai-stp-probe")
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    leaf_only = root / "a" / "b" / "leaf"
    full_chain = root / "c" / "d" / "leaf"
    ungranted = root / "e" / "f" / "leaf"
    for place in (leaf_only, full_chain, ungranted):
        place.mkdir(parents=True)
        (place / "marker.txt").write_text("x", encoding="utf-8")

    package = report.get("package_sid")

    def icacls(target: Path, rights: str, *, inherit: bool = True) -> dict[str, Any]:
        scope = "(OI)(CI)" if inherit else ""
        done = subprocess.run(
            ["icacls", str(target), "/grant", f"*{package}:{scope}{rights}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return {"rc": done.returncode, "out": (done.stdout + done.stderr).strip()[:120]}

    # The decisive comparison. `#51` says AppContainer "does not reach an
    # arbitrary target without editing the parents' DACLs"; bypass traverse
    # checking is granted to Everyone by default, so if an AppContainer token
    # keeps it, `leaf_only` reads and the objection is wrong. If only
    # `full_chain` reads, the objection is right and the cost of the design is
    # an ACE on every ancestor.
    # `(OI)(CI)` propagates to every descendant, so granting it on the root
    # reaches the tree that has to stay ungranted. The first run did exactly
    # that and all three leaves read, including the one granted nothing: a
    # negative control that could not fail, inside the probe written to avoid
    # one. The root and the intermediate directories therefore take a
    # this-folder-only ACE, which is traversal and nothing more.
    grants: dict[str, Any] = {"root_this_folder_only": icacls(root, "(RX)", inherit=False)}
    grants["leaf_only_leaf"] = icacls(leaf_only, "(RX)")
    for ancestor in (root / "c", root / "c" / "d"):
        grants[f"full_chain:{ancestor.name}"] = icacls(ancestor, "(RX)", inherit=False)
    grants["full_chain:leaf"] = icacls(full_chain, "(RX)")
    grants["runtime"] = icacls(Path(sys.executable).parent, "(RX)")
    # `ungranted` gets nothing, and neither do `a` and `b`.

    report["grants"] = grants

    # The container's own folder is the one place it can always write, so the
    # result never depends on the thing being measured. The previous run wrote
    # into a granted temp directory and produced no file at all, which said
    # nothing about why.
    userenv.GetAppContainerFolderPath.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPWSTR)]
    userenv.GetAppContainerFolderPath.restype = ctypes.c_long
    folder = wintypes.LPWSTR()
    hr = userenv.GetAppContainerFolderPath(package, ctypes.byref(folder))
    report["container_folder_hresult"] = hex(hr & 0xFFFFFFFF)
    if hr < 0:
        report["verdict"] = "no container folder; cannot collect the child's answer"
        print(json.dumps(report, indent=1, sort_keys=True))
        return 0
    home = Path(folder.value)
    report["container_folder"] = str(home)

    # The script lives in the container's own folder rather than in the tree
    # under test. The previous run granted it `(RX)` where it stood and Python
    # still reported `Errno 13` on it, so the script's reachability was a second
    # variable inside an experiment with room for one. A container owns this
    # directory by construction, which takes the question out of the result.
    script = home / "child.py"
    script.write_text("import subprocess\n" + CHILD, encoding="utf-8")
    result = home / "probe-result.json"

    quoted = json.dumps(ports).replace(chr(34), chr(92) + chr(34))
    argv = f'"{sys.executable}" "{script}" "{quoted}" "{leaf_only}" "{ungranted}" "{full_chain}"'
    report["child"] = _launch_in_container(kernel, sid, argv, result)

    # `sendto` returns success on a datagram the filter drops, so the sender's
    # own report says nothing. The receiving socket is the only witness: the
    # child was told to send a known token, and whether it arrived is the
    # measurement. A previous run recorded `dns_udp: "sent"` and that was a
    # statement about the call, not about the network.
    dns.settimeout(2.0)
    try:
        observed, _peer = dns.recvfrom(64)
    except OSError as error:
        report["dns_udp_arrived"] = f"no:{type(error).__name__}"
    else:
        report["dns_udp_arrived"] = f"yes:{observed[:16]!r}"
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


def _launch_in_container(kernel: Any, sid: Any, argv: str, _unused: Path) -> Any:
    """Run one command in an AppContainer and read its answer through a pipe.

    The answer comes back on an inherited handle rather than through a file,
    and that is the whole point. Three runs collected it from the filesystem —
    a granted temp directory, then the container's own profile folder — and all
    three returned exit 1 with no file and therefore no reason. A collection
    channel that depends on the thing being measured cannot report that the
    thing being measured failed.

    A handle is already open when the child receives it, so no path is resolved
    and no ACL is consulted on the child's side.
    """

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
            ("lpAttributeList", ctypes.c_void_p),
        ]

    class SECURITY_CAPABILITIES(ctypes.Structure):
        _fields_ = [
            ("AppContainerSid", ctypes.c_void_p),
            ("Capabilities", ctypes.c_void_p),
            ("CapabilityCount", wintypes.DWORD),
            ("Reserved", wintypes.DWORD),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    attributes = SECURITY_ATTRIBUTES()
    attributes.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    attributes.bInheritHandle = True
    read_end, write_end = wintypes.HANDLE(), wintypes.HANDLE()
    if not kernel.CreatePipe(
        ctypes.byref(read_end), ctypes.byref(write_end), ctypes.byref(attributes), 0
    ):
        return {"error": f"CreatePipe {ctypes.get_last_error()}"}
    # The read end must not travel to the child, or the parent's read never
    # sees end-of-file when the child exits.
    kernel.SetHandleInformation(read_end, 0x00000001, 0)

    size = ctypes.c_size_t(0)
    kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    if not kernel.InitializeProcThreadAttributeList(buffer, 1, 0, ctypes.byref(size)):
        return {"error": f"InitializeProcThreadAttributeList {ctypes.get_last_error()}"}

    caps = SECURITY_CAPABILITIES(
        AppContainerSid=sid, Capabilities=None, CapabilityCount=0, Reserved=0
    )
    if not kernel.UpdateProcThreadAttribute(
        buffer,
        0,
        ctypes.c_size_t(0x00020009),
        ctypes.byref(caps),
        ctypes.sizeof(caps),
        None,
        None,
    ):
        return {"error": f"UpdateProcThreadAttribute {ctypes.get_last_error()}"}

    start = STARTUPINFOEXW()
    start.cb = ctypes.sizeof(STARTUPINFOEXW)

    start.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
    start.hStdOutput = write_end
    start.hStdError = write_end
    start.hStdInput = None
    start.lpAttributeList = ctypes.cast(buffer, ctypes.c_void_p)

    info = PROCESS_INFORMATION()
    created = kernel.CreateProcessW(
        None,
        ctypes.create_unicode_buffer(argv),
        None,
        None,
        True,
        0x00080000 | 0x08000000,
        None,
        None,
        ctypes.byref(start),
        ctypes.byref(info),
    )
    if not created:
        return {
            "error": f"CreateProcessW {ctypes.get_last_error()}",
            "note": "no AppContainer could be launched on this host",
        }
    kernel.CloseHandle(write_end)

    chunks: list[bytes] = []
    piece = ctypes.create_string_buffer(4096)
    read = wintypes.DWORD()
    while kernel.ReadFile(read_end, piece, 4096, ctypes.byref(read), None) and read.value:
        chunks.append(piece.raw[: read.value])
    kernel.WaitForSingleObject(info.hProcess, 60000)
    code = wintypes.DWORD()
    kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel.CloseHandle(read_end)

    text = b"".join(chunks).decode("utf-8", errors="replace").strip()
    for line in reversed(text.splitlines()):
        try:
            return {"exit_code": code.value, "result": json.loads(line)}
        except ValueError:
            continue
    return {"exit_code": code.value, "raw": text[:1500] or "<the child wrote nothing>"}


if __name__ == "__main__":
    raise SystemExit(main())
