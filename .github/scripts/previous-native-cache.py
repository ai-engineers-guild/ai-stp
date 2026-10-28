"""Identify cached historical executables; runtime acceptance stays with the CI owner."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("cache_directory_invalid")
    expected_files = {"ai-stp"} if mode == "create" else {"ai-stp", "record.json"}
    if {item.name for item in root.iterdir()} != expected_files:
        raise ValueError("cache_files_invalid")
    binary = root / "ai-stp"
    info = binary.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o755
        or not 4096 < info.st_size <= 512 * 1024 * 1024
    ):
        raise ValueError("cache_executable_invalid")
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("cache_executable_format_invalid")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    expected = {
        "format": "ai-stp-previous-native-binary/1",
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
