"""Identify cached historical executables; runtime acceptance stays with the CI owner."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import stat
import sys
from pathlib import Path


def check(root: Path, commit: str, tree: str, recipe: str, compiler: str, mode: str) -> str:
    if (
        mode not in {"create", "verify"}
        or not re.fullmatch(r"[0-9a-f]{40}", commit)
        or not re.fullmatch(r"[0-9a-f]{40}", tree)
        or not re.fullmatch(r"[0-9a-f]{64}", recipe)
        or not compiler
        or len(compiler) > 8192
    ):
        raise ValueError("producer_identity_invalid")
    targets = {
        "linux": ("x86_64-unknown-linux-gnu", {"x86_64", "amd64"}, "ai-stp"),
        "darwin": ("aarch64-apple-darwin", {"arm64", "aarch64"}, "ai-stp"),
        "win32": ("x86_64-pc-windows-msvc", {"amd64", "x86_64"}, "ai-stp.exe"),
    }
    if sys.platform not in targets:
        raise ValueError("cache_host_invalid")
    target, machines, filename = targets[sys.platform]
    if (
        platform.machine().lower() not in machines
        or compiler.splitlines().count(f"host: {target}") != 1
    ):
        raise ValueError("cache_compiler_host_invalid")
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("cache_directory_invalid")
    expected_files = {filename} if mode == "create" else {filename, "record.json"}
    if {item.name for item in root.iterdir()} != expected_files:
        raise ValueError("cache_files_invalid")
    binary = root / filename
    info = binary.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or (sys.platform != "win32" and stat.S_IMODE(info.st_mode) != 0o755)
        or not 4096 < info.st_size <= 512 * 1024 * 1024
    ):
        raise ValueError("cache_executable_invalid")
    with binary.open("rb") as stream:
        header = stream.read(4096)
        if sys.platform == "linux":
            valid = header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\x3e\x00"
        elif sys.platform == "darwin":
            valid = header[:8] == b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01"
        else:
            offset = int.from_bytes(header[60:64], "little")
            valid = (
                header[:2] == b"MZ"
                and 64 <= offset <= len(header) - 6
                and header[offset : offset + 6] == b"PE\x00\x00\x64\x86"
            )
        if not valid:
            raise ValueError("cache_executable_format_invalid")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    expected = {
        "format": "ai-stp-previous-native-binary/2",
        "target": target,
        "binary": filename,
        "source_commit": commit,
        "source_tree": tree,
        "producer_recipe_sha256": recipe,
        "compiler": compiler,
        "binary_sha256": digest,
        "binary_bytes": info.st_size,
    }
    record = root / "record.json"
    encoded = (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if mode == "create":
        with record.open("xb") as stream:
            stream.write(encoded)
    else:
        info = record.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 32768:
            raise ValueError("cache_record_invalid")
        if record.read_bytes() != encoded:
            raise ValueError("cache_record_mismatch")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    for name in ("commit", "tree", "recipe", "compiler"):
        parser.add_argument(name)
    parser.add_argument("mode", choices=("create", "verify"))
    args = parser.parse_args()
    try:
        digest = check(args.root, args.commit, args.tree, args.recipe, args.compiler, args.mode)
    except (OSError, ValueError) as error:
        print(f"Previous writer cache refused ({type(error).__name__}).", file=sys.stderr)
        return 1
    print(f"Previous writer cache {args.mode}: source={args.commit} binary_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
