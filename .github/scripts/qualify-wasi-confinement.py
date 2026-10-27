"""Qualify one identical disposable WASIp2 component on three actual CI OSes."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import select
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.request
import zipfile
from pathlib import Path

VERSION = "50.0.0"
# Official v50.0.0 GitHub release asset digests, not mutable latest URLs.
RUNTIMES = {
    ("Linux", "x86_64"): (
        "x86_64-linux.tar.xz",
        "77c19ee0437991f9ac7837b9c269d9c7076744f85dad263fea5214cc2723c7ff",
    ),
    ("Darwin", "arm64"): (
        "aarch64-macos.tar.xz",
        "323dc098dc0455d60f396c404627e967b7033ffcfa29abfffb243126cf82c9d6",
    ),
    ("Windows", "amd64"): (
        "x86_64-windows.zip",
        "cea9ccc700aaccb2b5507e96ac990ba60104bd7ab39284fb2e67cb64d58efcc4",
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(
    arguments: list[str], *, timeout: int = 120, **kwargs: object
) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, capture_output=True, timeout=timeout, check=False, **kwargs)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise RuntimeError("Fixed fixture exceeded its bounded diagnostic output")
    return result


def checked(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    result = run(arguments, **kwargs)
    if result.returncode:
        print((result.stdout + result.stderr).decode("utf-8", errors="replace"), flush=True)
        result.check_returncode()
    return result


def require_ci() -> tuple[Path, Path]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Disposable actual CI required; no local toolchain installation")
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    if temporary.is_relative_to(workspace):
        raise RuntimeError("Fixture output must remain outside the checkout")
    return workspace, temporary


def component(path: Path) -> bytes:
    data = path.read_bytes()
    if not 8 < len(data) < 16 * 1024 * 1024 or data[:8] != b"\x00asm\x0d\x00\x01\x00":
        raise RuntimeError("Expected bounded portable component bytes, never native/AOT code")
    return data


def build(workspace: Path, output: Path) -> None:
    if platform.system() != "Linux" or output.exists():
        raise RuntimeError("One Linux producer and a new owned output directory required")
    pin = tomllib.loads((workspace / "apps/cli/rust-toolchain.toml").read_text())["toolchain"][
        "channel"
    ]
    output.mkdir()
    checked(
        [
            "rustc",
            "+" + pin,
            "--edition=2024",
            "-Dwarnings",
            "-Copt-level=1",
            "--target",
            "wasm32-wasip2",
            str(workspace / "tests/native_confinement/wasi.rs"),
            "-o",
            str(output / "fixture.wasm"),
        ],
        timeout=180,
    )
    data = component(output / "fixture.wasm")
    manifest = {
        "format": 1,
        "consumer_revision": os.environ["GITHUB_SHA"],
        "rust_toolchain": pin,
        "guest_source_sha256": digest(
            (workspace / "tests/native_confinement/wasi.rs").read_bytes()
        ),
        "component_sha256": digest(data),
        "bytes": len(data),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    print(json.dumps({"producer": manifest}), flush=True)


def install_runtime(root: Path) -> tuple[Path, str]:
    suffix, expected = RUNTIMES[(platform.system(), platform.machine().lower())]
    name = f"wasmtime-v{VERSION}-{suffix}"
    url = f"https://github.com/bytecodealliance/wasmtime/releases/download/v{VERSION}/{name}"
    with urllib.request.urlopen(url, timeout=60) as response:
        archive = response.read(32 * 1024 * 1024 + 1)
    if len(archive) > 32 * 1024 * 1024 or digest(archive) != expected:
        raise RuntimeError("Pinned official runtime asset digest mismatch")
    executable = "wasmtime.exe" if platform.system() == "Windows" else "wasmtime"
    if suffix.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            matches = [p for p in bundle.infolist() if Path(p.filename).name == executable]
            if len(matches) != 1 or matches[0].file_size > 64 * 1024 * 1024:
                raise RuntimeError("Expected one bounded runtime executable")
            data = bundle.read(matches[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as bundle:
            matches = [p for p in bundle.getmembers() if Path(p.name).name == executable]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 64 * 1024 * 1024:
                raise RuntimeError("Expected one bounded regular runtime executable")
            member = bundle.extractfile(matches[0])
            if member is None:
                raise RuntimeError("Runtime member unavailable")
            data = member.read()
    binary = root / executable
    binary.write_bytes(data)
    binary.chmod(0o700)
    observed = checked([str(binary), "--version"]).stdout.decode().strip()
    if not observed.startswith(f"wasmtime {VERSION} "):
        raise RuntimeError("Runtime version readback mismatch")
    print(json.dumps({"runtime": observed, "asset_sha256": expected}), flush=True)
    return binary, expected


def endpoint(stack: contextlib.ExitStack, family: int, kind: int) -> socket.socket:
    listener = stack.enter_context(socket.socket(family, kind))
    listener.settimeout(2)
    listener.bind(("127.0.0.1" if family == socket.AF_INET else "::1", 0))
    if kind == socket.SOCK_STREAM:
        listener.listen(4)
    with socket.socket(family, kind) as positive:
        positive.settimeout(2)
        if kind == socket.SOCK_STREAM:
            positive.connect(listener.getsockname())
            accepted, _ = listener.accept()
            with accepted:
                positive.sendall(b"positive")
                if accepted.recv(32) != b"positive":
                    raise RuntimeError("TCP host positive control failed")
        else:
            positive.sendto(b"positive", listener.getsockname())
            if listener.recvfrom(32)[0] != b"positive":
                raise RuntimeError("UDP host positive control failed")
    return listener


def address(listener: socket.socket) -> str:
    host, port = listener.getsockname()[:2]
    return f"[{host}]:{port}" if listener.family == socket.AF_INET6 else f"{host}:{port}"


def exercise(workspace: Path, temporary: Path, artifact: Path) -> None:
    manifest = json.loads((artifact / "manifest.json").read_text())
    data = component(artifact / "fixture.wasm")
    pin = tomllib.loads((workspace / "apps/cli/rust-toolchain.toml").read_text())["toolchain"][
        "channel"
    ]
    if manifest != {
        "format": 1,
        "consumer_revision": os.environ["GITHUB_SHA"],
        "rust_toolchain": pin,
        "guest_source_sha256": digest(
            (workspace / "tests/native_confinement/wasi.rs").read_bytes()
        ),
        "component_sha256": digest(data),
        "bytes": len(data),
    }:
        raise RuntimeError("Exact source/producer/component manifest mismatch")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ai-stp-wasi-", dir=temporary) as owned:
        root = Path(owned).resolve(strict=True)
        binary, runtime_digest = install_runtime(root)
        target, outside = root / "target", root / "outside"
        target.mkdir()
        outside.mkdir()
        (target / "canary").write_bytes(b"synthetic target\n")
        for leaf in ["canary", "credentials"]:
            (outside / leaf).write_bytes(b"synthetic outside\n")
        link = target / "escape"
        link_method = "symlink"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if platform.system() != "Windows":
                raise
            # A new disposable junction only; no privilege/ACL changes or existing path.
            if link.exists() or link.is_symlink():
                raise RuntimeError("Absent owned junction path required") from None
            checked([os.environ["COMSPEC"], "/d", "/c", "mklink", "/J", str(link), str(outside)])
            link_method = "junction"
        if (link / "canary").read_bytes() != b"synthetic outside\n":
            raise RuntimeError("Physical escape fixture host positive failed")
        original = {
            p: p.read_bytes()
            for p in [target / "canary", outside / "canary", outside / "credentials"]
        }
        physical = target.stat()
        # Configure only the runtime subprocess, never the host's persistent environment.
        environment = {k: v for k, v in os.environ.items() if not k.startswith("WASMTIME_")}
        environment["AI_STP_SYNTHETIC_SECRET"] = "disposable host environment canary"
        base = [
            str(binary),
            "run",
            "-Ccache=false",
            "-Wfuel=20000000,max-memory-size=67108864,max-wasm-stack=1048576,timeout=10s",
            "-Scli=true,p3=false,inherit-env=false,inherit-stdin=false,inherit-network=false,"
            "tcp=false,udp=false,allow-ip-name-lookup=false,max-resources=128,"
            "max-component-handles=1024,hostcall-fuel=1048576",
            "--dir",
            str(target) + "::/target",
            "--env",
            "AI_STP_GUEST=controlled",
        ]
        with contextlib.ExitStack() as stack:
            endpoints = [
                endpoint(stack, family, kind)
                for kind in [socket.SOCK_STREAM, socket.SOCK_DGRAM]
                for family in [socket.AF_INET, socket.AF_INET6]
            ]
            result = checked(
                [
                    *base,
                    str(artifact / "fixture.wasm"),
                    "probe",
                    str(outside / "canary"),
                    str(outside / "credentials"),
                    *map(address, endpoints),
                    sys.executable,
                ],
                env=environment,
                cwd=root,
                timeout=30,
            )
            print(result.stdout.decode(), end="", flush=True)
            if select.select(endpoints, [], [], 0)[0]:
                raise RuntimeError("Guest caused an unexpected loopback effect")
        if (target / "probe_completed").read_bytes() != b"completed\n":
            raise RuntimeError("Actual guest completion marker missing")
        memory = checked(
            [*base, str(artifact / "fixture.wasm"), "memory"], env=environment, cwd=root, timeout=30
        )
        print(memory.stdout.decode(), end="", flush=True)
        if (target / "memory_refused").read_bytes() != b"refused\n":
            raise RuntimeError("Actual guest memory limit marker missing")
        spin = run(
            [*base, str(artifact / "fixture.wasm"), "spin"], env=environment, cwd=root, timeout=30
        )
        if (
            spin.returncode == 0
            or (target / "spin_started").read_bytes() != b"started\n"
            or b"all fuel consumed" not in spin.stderr
        ):
            print((spin.stdout + spin.stderr).decode(errors="replace"), flush=True)
            raise RuntimeError("Expected executed guest and exact fuel exhaustion trap")
        ungranted = root / "ungranted.wat"
        ungranted.write_text(
            '(module (import "ai-stp-ungranted" "host-process" (func)) (func (export "_start")))\n'
        )
        refused = run([*base, str(ungranted)], env=environment, cwd=root, timeout=30)
        if refused.returncode == 0 or b"unknown import" not in refused.stderr:
            print((refused.stdout + refused.stderr).decode(errors="replace"), flush=True)
            raise RuntimeError("Unregistered host-process import must fail linking")
        current = target.stat()
        if (physical.st_dev, physical.st_ino) != (current.st_dev, current.st_ino):
            raise RuntimeError("Physical target identity changed")
        if any(p.read_bytes() != expected for p, expected in original.items()):
            raise RuntimeError("Host canary bytes changed")
        print(
            json.dumps(
                {
                    "wasi_confinement": "passed",
                    "os": platform.system(),
                    "component_sha256": digest(data),
                    "consumer_revision": os.environ["GITHUB_SHA"],
                    "runtime_asset_sha256": runtime_digest,
                    "escape_fixture": link_method,
                    "parent_proven_loopback_transports": 4,
                    "fuel_exhaustion_after_guest_started": True,
                    "memory_positive_and_limit": True,
                    "unregistered_host_process_import_refused": True,
                    "executed_native_descendant": False,
                    "production_artifact_family_selected": False,
                    "all_seven_installers_qualified": False,
                    "product_packaging_qualified": False,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            ),
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["build", "exercise"])
    parser.add_argument("artifact", type=Path)
    arguments = parser.parse_args()
    workspace, temporary = require_ci()
    artifact = arguments.artifact.resolve()
    if not artifact.is_relative_to(temporary):
        raise RuntimeError("Only disposable runner-temp artifacts permitted")
    if arguments.mode == "build":
        build(workspace, artifact)
    else:
        exercise(workspace, temporary, artifact.resolve(strict=True))


if __name__ == "__main__":
    main()
