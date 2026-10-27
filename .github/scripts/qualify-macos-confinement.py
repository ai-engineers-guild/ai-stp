"""Build a disposable signed helper with implicit bookmarks on an actual macOS runner."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


def run(arguments: list[str], timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(arguments, check=False, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        # Compiler and ad-hoc signing diagnostics concern only this disposable fixture.
        print((result.stdout + result.stderr)[:16384].decode("utf-8", errors="replace"), flush=True)
        result.check_returncode()
    return result


def verify_entitlements(path: Path, expected: dict[str, bool]) -> None:
    run(["codesign", "--verify", "--strict", str(path)])
    # TN3125: the default is human-readable DER; request XML for a plist parser.
    observed = run(["codesign", "--display", "--entitlements", "-", "--xml", str(path)])
    if plistlib.loads(observed.stdout) != expected:
        raise RuntimeError("Signed entitlement readback differs from the exact fixture")
    print(json.dumps({"verified_sandbox_entitlements": sorted(expected)}), flush=True)


def main() -> None:
    if (
        sys.platform != "darwin"
        or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_OS") != "macOS"
    ):
        raise RuntimeError("Actual disposable macOS CI required")
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)
    source = workspace / "tests/native_confinement/macos.mm"
    identifier = "ai.stp.confinement." + uuid.uuid4().hex
    containers = (Path.home() / "Library/Containers").resolve()
    container = containers / identifier
    if container.exists() or container.is_symlink():
        raise RuntimeError("Only an absent unique fixture container may be admitted")
    try:
        with tempfile.TemporaryDirectory(
            prefix="ai-stp-macos-confinement-", dir=temporary
        ) as owned:
            root = Path(owned).resolve(strict=True)
            fixture = root / "fixture"
            for leaf in ["target", "outside"]:
                (fixture / leaf).mkdir(parents=True)
            for leaf in ["target/canary", "outside/canary", "outside/credentials"]:
                (fixture / leaf).write_bytes(b"synthetic fixture\n")
            controller = root / "controller"
            run(["xcrun", "--find", "clang++"])
            run(
                [
                    "xcrun",
                    "clang++",
                    "-std=c++20",
                    "-fobjc-arc",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-O2",
                    "-framework",
                    "Foundation",
                    "-framework",
                    "AppKit",
                    str(source),
                    "-o",
                    str(controller),
                ]
            )
            bundle = root / "Probe.app"
            executable = bundle / "Contents/MacOS/worker"
            child = bundle / "Contents/Helpers/child"
            executable.parent.mkdir(parents=True)
            child.parent.mkdir(parents=True)
            shutil.copy2(controller, executable)
            shutil.copy2(controller, child)
            info = {
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "worker",
                "CFBundleName": "Disposable confinement experiment",
                "CFBundlePackageType": "APPL",
                "CFBundleVersion": "1.0",
                "CFBundleShortVersionString": "1.0",
            }
            (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
            worker_rights = {
                "com.apple.security.app-sandbox": True,
                "com.apple.security.files.user-selected.read-write": True,
            }
            child_rights = {
                "com.apple.security.app-sandbox": True,
                "com.apple.security.inherit": True,
            }
            brokers: list[tuple[str, Path, dict[str, bool]]] = []
            for role in ["positive", "worker", "child"]:
                broker = fixture / "target" / ("Broker-" + role + ".app")
                binary = broker / "Contents/MacOS/broker"
                binary.parent.mkdir(parents=True)
                shutil.copy2(controller, binary)
                name = identifier + ".broker." + role
                broker_info = {
                    **info,
                    "CFBundleIdentifier": name,
                    "CFBundleExecutable": "broker",
                    "LSBackgroundOnly": True,
                    "AiStpFixtureRoot": str(fixture),
                    "AiStpFixtureRole": role,
                }
                (broker / "Contents/Info.plist").write_bytes(plistlib.dumps(broker_info))
                brokers.append((name, broker, {}))
            for name, path, entitlements in [
                (identifier + ".child", child, child_rights),
                *brokers,
                (identifier, bundle, worker_rights),
            ]:
                entitlement_file = root / (name + ".plist")
                entitlement_file.write_bytes(plistlib.dumps(entitlements))
                run(
                    [
                        "codesign",
                        "--force",
                        "--sign",
                        "-",
                        "--identifier",
                        name,
                        "--entitlements",
                        str(entitlement_file),
                        str(path),
                    ]
                )
                verify_entitlements(path, entitlements)
            run(["codesign", "--verify", "--strict", "--deep", str(bundle)])
            result = subprocess.run(
                [str(controller), "controller", str(fixture), str(executable), str(child)],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if len(result.stdout) > 16384:
                raise RuntimeError("Native fixture exceeded its bounded proof output")
            print(result.stdout.decode("utf-8"), end="", flush=True)
            if result.returncode != 0:
                raise RuntimeError("The actual signed macOS helper experiment refused")
            proof = json.loads(result.stdout)
            if proof.get("macos_confinement_experiment") != "passed":
                raise RuntimeError("Actual helper proof is absent")
    finally:
        # This exact UUID was absent at admission; never touch existing containers.
        if container.is_symlink():
            raise RuntimeError("Owned fixture container was replaced by a symlink")
        if container.exists():
            shutil.rmtree(container)
    print(json.dumps({"owned_cleanup": True, "release_or_provider_runtime_enabled": False}))


if __name__ == "__main__":
    main()
