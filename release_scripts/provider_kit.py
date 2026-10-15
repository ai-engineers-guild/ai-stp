"""Verify the immutable provider kit and synchronize its served wire schemas.

The published kit is the wire contract. Its original generator is retained on
legacy/python-cli; changing that implementation must never rewrite released bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT_VERSION = "0.2.17"
AGGREGATE = "sha256:c0644fd07ebdea6232085dee1eda5d6175ed368294e92f2d1e2a4b9c363cbeaf"
API_SCHEMAS = ROOT / "apps/api/src/ai_stp_api/slices/schemas"


def synchronize(output: Path, *, check: bool) -> tuple[str, ...]:
    checksums = (output / "SHA256SUMS").read_bytes()
    identity = json.loads((output / "KIT-IDENTITY.json").read_bytes())
    digest = "sha256:" + hashlib.sha256(checksums).hexdigest()
    if digest != AGGREGATE or identity["aggregate_digest"] != digest:
        return ("published provider kit aggregate changed",)
    if identity["kit_version"] != KIT_VERSION:
        return ("published provider kit version changed",)
    rows = [line.split() for line in checksums.decode().splitlines()]
    names = [name for _, name in rows]
    if sorted(names) != sorted(identity["files"]) or len(set(names)) != len(names):
        return ("provider kit file set differs from its identity",)
    problems = []
    for expected, name in rows:
        if Path(name).name != name:
            return ("invalid provider kit member",)
        path = output / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(str(path))
    if problems:
        return tuple(problems)
    for name in ("provider-info.schema.json", "status-response.schema.json"):
        content = (output / name).read_bytes()
        path = API_SCHEMAS / name
        if path.is_file() and path.read_bytes() == content:
            continue
        if check:
            problems.append(str(path))
        else:
            path.write_bytes(content)
    return tuple(problems)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    problems = synchronize(arguments.output, check=arguments.check)
    for problem in problems:
        print(problem)
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
