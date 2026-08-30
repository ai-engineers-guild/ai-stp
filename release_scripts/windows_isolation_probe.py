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
import socket
import subprocess
import sys
import tempfile
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
for label, target in (("granted_target", grant), ("ungranted_target", deny)):
    try:
        out[label] = sorted(p.name for p in Path(target).iterdir())[:3] or ["<empty>"]
    except OSError as exc:
        out[label] = "denied:" + type(exc).__name__
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
    except Exception as exc:  # noqa: BLE001
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

    root = Path(tempfile.mkdtemp(prefix="ai-stp-probe-"))
    granted, ungranted = root / "granted", root / "ungranted"
    for place in (granted, ungranted):
        place.mkdir(parents=True)
        (place / "marker.txt").write_text("x", encoding="utf-8")

    # Grant only the leaf, and deliberately not its parents: `#51` says this is
    # the step that does not reach. Bypass-traverse-checking is granted to
    # Everyone by default, so the question is whether an AppContainer keeps it.
    grant = subprocess.run(
        ["icacls", str(granted), "/grant", f"*{report.get('package_sid')}:(OI)(CI)(RX)"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    report["icacls_returncode"] = grant.returncode
    report["icacls_output"] = (grant.stdout + grant.stderr).strip()[:300]

    script = root / "child.py"
    script.write_text("import subprocess\n" + CHILD, encoding="utf-8")
    argv = f'"{sys.executable}" "{script}" "{json.dumps(ports).replace(chr(34), chr(92) + chr(34))}" "{granted}" "{ungranted}"'
    report["child"] = _launch_in_container(kernel, sid, argv, report)
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


def _launch_in_container(kernel: Any, sid: Any, argv: str, report: dict[str, Any]) -> Any:
    """CreateProcessW with PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES."""

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
    start.lpAttributeList = ctypes.cast(buffer, ctypes.c_void_p)
    info = PROCESS_INFORMATION()
    out = Path(tempfile.mkstemp(suffix=".json")[1])
    # The container cannot inherit our handles usefully, so it writes a file it
    # was granted instead. Simpler: run through cmd and redirect.
    full = f'cmd.exe /c {argv} > "{out}" 2>&1'
    created = kernel.CreateProcessW(
        None,
        ctypes.create_unicode_buffer(full),
        None,
        None,
        False,
        0x00080000 | 0x08000000,
        None,
        None,
        ctypes.byref(start),
        ctypes.byref(info),
    )
    if not created:
        return {
            "error": f"CreateProcessW {ctypes.get_last_error()}",
            "note": "an AppContainer cannot be created this way on this host",
        }
    kernel.WaitForSingleObject(info.hProcess, 60000)
    code = wintypes.DWORD()
    kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    text = out.read_text(encoding="utf-8", errors="replace").strip()
    try:
        os.unlink(out)
    except OSError:
        pass
    try:
        return {"exit_code": code.value, "result": json.loads(text.splitlines()[-1])}
    except Exception:  # noqa: BLE001
        return {"exit_code": code.value, "raw": text[:1200]}


if __name__ == "__main__":
    raise SystemExit(main())
