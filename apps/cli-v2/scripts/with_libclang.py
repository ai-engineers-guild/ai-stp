"""Expose the installed libclang build prerequisite; never download a toolchain.

The native build owns this adapter for sqlite-plugin's bindgen bridge. Remove it
with that dependency. libclang is a build-time dependency, not a shipped library.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def prepend(env: dict[str, str], key: str, value: str) -> None:
    env[key] = os.pathsep.join(part for part in (value, env.get(key, "")) if part)


def main(arguments: list[str]) -> int:
    if not arguments:
        raise SystemExit("with_libclang requires a command")
    env = os.environ.copy()
    if sys.platform == "win32":
        return subprocess.call(arguments, env=env)
    if sys.platform == "darwin":
        compiler = Path(subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip())
        directory = compiler.parent.parent / "lib"
        sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
        resources = subprocess.check_output(
            [str(compiler), "-print-resource-dir"], text=True
        ).strip()
        if not (directory / "libclang.dylib").is_file():
            raise SystemExit("the selected Xcode toolchain lacks libclang")
        env["LIBCLANG_PATH"] = str(directory)
        prepend(env, "DYLD_FALLBACK_LIBRARY_PATH", str(directory))
        flags = ["-isysroot", sdk, "-isystem", str(Path(resources) / "include")]
        env["BINDGEN_EXTRA_CLANG_ARGS"] = (
            shlex.join(flags) + " " + env.get("BINDGEN_EXTRA_CLANG_ARGS", "")
        )
        return subprocess.call(arguments, env=env)
    if sys.platform != "linux":
        raise SystemExit("native builds support Linux, macOS and Windows")
    configured = env.get("LIBCLANG_PATH")
    directories = (
        [Path(configured)]
        if configured
        else sorted(Path("/usr/lib").glob("llvm-*/lib"), reverse=True)
    )
    libraries = []
    for directory in directories:
        if directory.is_file():
            libraries.append(directory)
        else:
            libraries.extend(sorted(directory.glob("libclang.so*")))
    library = next((path.resolve() for path in libraries if path.is_file()), None)
    if library is None:
        raise SystemExit(
            "install libclang development files or set LIBCLANG_PATH to their directory"
        )
    include = Path(subprocess.check_output(["cc", "-print-file-name=include"], text=True).strip())
    if not include.is_absolute() or not (include / "stdarg.h").is_file():
        raise SystemExit("the C compiler's standard headers are unavailable")
    # Runtime-only installations may omit the unversioned linker name. A local
    # symlink also avoids retaining deleted loader paths in restored Cargo caches.
    with tempfile.TemporaryDirectory(prefix="ai-stp-libclang-") as temporary:
        directory = Path(temporary)
        (directory / "libclang.so").symlink_to(library)
        env["LIBCLANG_PATH"] = temporary
        prepend(env, "LIBRARY_PATH", temporary)
        prepend(env, "LD_LIBRARY_PATH", str(library.parent))
        prepend(env, "LD_LIBRARY_PATH", temporary)
        env["BINDGEN_EXTRA_CLANG_ARGS"] = (
            shlex.join(["-isystem", str(include)]) + " " + env.get("BINDGEN_EXTRA_CLANG_ARGS", "")
        )
        return subprocess.call(arguments, env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
