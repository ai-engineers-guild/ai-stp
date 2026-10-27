"""Measure locked, unmodified seven-provider WASIp2 compilation only in CI."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import tarfile
import time
import tomllib
import urllib.request
from pathlib import Path

SDK = "wasi-sdk-34.0-x86_64-linux"
SDK_SHA256 = "b761e3a0721dbae9c09a0059e5fdb2bf917d1b4a8a7b430fb3b5aafb0984b2c4"
PROVIDERS = [
    (
        "codex",
        "676969e8723231c26e731a62eab5ca5545f81ef2",
        "8eb7f7ba3b88f41056198d221554e382c7ba3485",
    ),
    (
        "claude",
        "45387d874721c01733724e3e5f934c9bbee1b19b",
        "80b4791804be36661abae0fe8ba662f8d4b30f0e",
    ),
    (
        "antigravity",
        "98cda14a4c33b9a3834fdb38f092f8a56bed7c4d",
        "6472dfd8968cbe12fd70024c9b92042c1eac7b32",
    ),
    (
        "grok",
        "5b9bbcd260c6cee86f635ed80e8b3ba6ed11372a",
        "a3fef6554390ef934cc23d3540e0881676388380",
    ),
    (
        "cursor",
        "8ec022fce75826a32fed44428909d28a676b4e97",
        "2d08eca391215219e89a986c18458854ad1d8c55",
    ),
    (
        "opencode",
        "61fcd397a8971fdb07d05da096baf777df087b82",
        "9ae5b47991c00fdb74e7e409b94380661760c33b",
    ),
    ("pi", "5347b39153286f6c382408d2213de6c93fa3ee8f", "920e6affa386cf1cd5d2c36f5fcc970b4b9d7d06"),
]
COMMON = {
    # Sorted paths relative to each src directory, NUL, then exact file bytes.
    "setup-core": "159b3ce97b9bccf24a00358666585690654850d8325dfde4b44df359bca55982",
    "provider-v3": "ebbc11aba8adc53ccbd3fe9c5071c40a458eafc35d56c2c2399e484b6d2ce985",
}


def command(arguments: list[str], root: Path, *, timeout: int = 40) -> bytes:
    return subprocess.run(
        arguments, cwd=root, check=True, capture_output=True, timeout=timeout
    ).stdout


def sdk(root: Path) -> Path:
    archive = root / (SDK + ".tar.gz")
    url = f"https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-34/{archive.name}"
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url, timeout=60) as response, archive.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 224 * 1024 * 1024:
                raise RuntimeError("Pinned SDK archive exceeded its bound")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != SDK_SHA256:
        raise RuntimeError("Official immutable SDK digest mismatch")
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if len(members) > 50000 or sum(item.size for item in members) > 2 * 1024**3:
            raise RuntimeError("Pinned SDK expanded inventory exceeded its bound")
        bundle.extractall(root, members=members, filter="data")
    archive.unlink()
    result = root / SDK
    if not (result / "bin/clang").is_file() or not (result / "share/wasi-sysroot").is_dir():
        raise RuntimeError("Pinned SDK compiler/sysroot absent")
    return result


def common(root: Path, crate: str) -> str:
    digest = hashlib.sha256()
    source = root / "crates" / crate / "src"
    for path in sorted(source.rglob("*.rs")):
        digest.update(path.relative_to(source).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or platform.system() != "Linux":
        raise RuntimeError("Disposable Linux CI only; never install an SDK locally")
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    if temporary.is_relative_to(workspace):
        raise RuntimeError("Temporary sources and artifacts must remain outside the checkout")
    pin = tomllib.loads((workspace / "apps/cli/rust-toolchain.toml").read_text())["toolchain"][
        "channel"
    ]
    consumer = command(["git", "rev-parse", "HEAD"], workspace).decode().strip()
    if consumer != os.environ["GITHUB_SHA"]:
        raise RuntimeError("Consumer checkout must equal the exact Actions source")
    root = temporary / "ai-stp-provider-portability"
    root.mkdir()
    compiler = sdk(root)
    environment = dict(
        os.environ,
        RUSTUP_TOOLCHAIN=pin,
        CARGO_BUILD_JOBS="2",
        CARGO_TARGET_DIR=str(root / "target"),
        CARGO_BUILD_BUILD_DIR=str(root / "build"),
        CC_wasm32_wasip2=str(compiler / "bin/clang"),
        AR_wasm32_wasip2=str(compiler / "bin/llvm-ar"),
        CFLAGS_wasm32_wasip2=f"--target=wasm32-wasip2 --sysroot={compiler / 'share/wasi-sysroot'}",
    )
    proofs = []
    for name, source, tree in PROVIDERS:
        package = name + "-setup-system"
        checkout = root / package
        checkout.mkdir()
        command(["git", "init", "--quiet"], checkout)
        origin = "https://github.com/NDDev-Technocracy-Archive/" + package + ".git"
        command(["git", "fetch", "--no-tags", "--depth=1", origin, source], checkout)
        if command(["git", "rev-parse", "FETCH_HEAD"], checkout).decode().strip() != source:
            raise RuntimeError("Exact immutable provider source required")
        if command(["git", "rev-parse", "FETCH_HEAD^{tree}"], checkout).decode().strip() != tree:
            raise RuntimeError("Exact reviewed provider tree required")
        command(["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"], checkout)
        for crate, expected in COMMON.items():
            if common(checkout, crate) != expected:
                raise RuntimeError("Common portability surface differs from the audited source")
        lock = hashlib.sha256((checkout / "Cargo.lock").read_bytes()).hexdigest()
        print(
            json.dumps({"stage": "locked-provider-build", "provider": package, "source": source}),
            flush=True,
        )
        started = time.monotonic()
        result = subprocess.run(
            [
                "cargo",
                "build",
                "--locked",
                "--release",
                "--target",
                "wasm32-wasip2",
                "--package",
                package,
                "--bin",
                package,
                "--message-format=json-render-diagnostics",
            ],
            cwd=checkout,
            env=environment,
            capture_output=True,
            timeout=600,
            check=False,
        )
        if len(result.stdout) + len(result.stderr) > 2 * 1024 * 1024:
            raise RuntimeError("Bounded compiler diagnostic inventory required")
        proof = {
            "provider": package,
            "source": source,
            "tree": tree,
            "lock_sha256": lock,
            "seconds": round(time.monotonic() - started, 3),
            "returncode": result.returncode,
        }
        executable = None
        for line in result.stdout.splitlines():
            message = json.loads(line)
            if (
                message.get("reason") == "compiler-artifact"
                and message.get("executable")
                and message["target"]["name"] == package
                and message["target"]["kind"] == ["bin"]
            ):
                executable = Path(message["executable"])
        if result.returncode == 0:
            if executable is None or not executable.resolve().is_relative_to(root / "target"):
                raise RuntimeError("Compiled portable artifact absent from the owned target")
            data = executable.read_bytes()
            if not 8 < len(data) < 32 * 1024 * 1024 or data[:8] != b"\0asm\r\0\1\0":
                raise RuntimeError("Expected portable component; never accept a native executable")
            proof["component_sha256"] = hashlib.sha256(data).hexdigest()
            proof["component_bytes"] = len(data)
        else:
            # Public pinned source/compiler output only, never session or vault data.
            print((result.stdout + result.stderr)[-65536:].decode(errors="replace"), flush=True)
        if hashlib.sha256((checkout / "Cargo.lock").read_bytes()).hexdigest() != lock:
            raise RuntimeError("Locked build changed its source lock")
        if command(["git", "status", "--porcelain"], checkout).strip():
            raise RuntimeError("Unmodified source compilation changed the provider checkout")
        proofs.append(proof)
        (root / "proof.json").write_text(
            json.dumps(
                {
                    "consumer": consumer,
                    "compiler": pin,
                    "sdk": SDK,
                    "sdk_sha256": SDK_SHA256,
                    "providers": proofs,
                    "runtime_qualified": False,
                    "production_family_enabled": False,
                },
                sort_keys=True,
            )
            + "\n"
        )
        print(json.dumps(proof), flush=True)
    if len(proofs) != 7 or any(item["returncode"] != 0 for item in proofs):
        raise RuntimeError("All seven actual locked portable builds are required; see owned proof")


if __name__ == "__main__":
    main()
