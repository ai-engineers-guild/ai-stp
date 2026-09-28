"""Check `scripts/safety/requirements.lock` was compiled from its `.in`.

A byte-diff against a fresh `uv pip compile` cannot be the gate: transitive
resolutions move under an unchanged `.in`, so the snapshot is never
reproducible twice. What can be asked deterministically, offline, is whether
the lock still answers this input — every pinned requirement in
`requirements.in` appears as a `-r requirements.in` member at the same
version — and whether every locked package carries the hashes
`--require-hashes` installs need. An `.in` edit without a recompile fails the
first; a stripped or partial lock fails the second.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "safety" / "requirements.in"
LOCK = ROOT / "scripts" / "safety" / "requirements.lock"

#: `pkg==1.2.3` lines in the `.in`; anything else (comments, extras) is not a
#: pinned requirement this check can verify.
PIN = re.compile(r"^([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9.!+*_-]+)\s*$")
#: `pkg==1.2.3 \` or `pkg==1.2.3` (last line of an entry) at lock top level.
ENTRY = re.compile(r"^([A-Za-z0-9_.-]+)\s*==\s*(\S+?)\s*\\?\s*$")
VIA_SOURCE = "-r scripts/safety/requirements.in"


def _source_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    problems: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        match = PIN.match(stripped)
        if not match:
            problems.append(f"unverifiable requirement line in {path.name}: {stripped}")
            continue
        pins[match.group(1).lower()] = match.group(2)
    if problems:
        raise ValueError("; ".join(problems))
    return pins


def check() -> list[str]:
    problems: list[str] = []
    if not LOCK.is_file():
        return [f"missing compiled lock: {LOCK}"]
    pins = _source_pins(SOURCE)
    direct: dict[str, str] = {}
    current: str | None = None
    entries: list[tuple[str, str, bool]] = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            if VIA_SOURCE in stripped and current is not None and entries:
                direct[current.lower()] = entries[-1][1]
            continue
        match = ENTRY.match(line)
        if match:
            name, version = match.group(1), match.group(2)
            entries.append((name, version, False))
            current = name
        if "--hash=sha256:" in line and entries:
            name, version, _ = entries[-1]
            entries[-1] = (name, version, True)
    for name, version, hashed in entries:
        if not hashed:
            problems.append(f"lock entry carries no sha256 hash: {name}=={version}")
    missing = sorted(set(pins) - set(direct))
    for name in missing:
        problems.append(f"requirement not compiled into the lock: {name}=={pins[name]}")
    for name in sorted(set(pins) & set(direct)):
        if direct[name] != pins[name]:
            problems.append(
                f"locked version {direct[name]} differs from {SOURCE.name} pin {pins[name]}: {name}"
            )
    extra = sorted(set(direct) - set(pins))
    for name in extra:
        problems.append(f"lock carries a {VIA_SOURCE} member the input no longer pins: {name}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    if arguments.check:
        try:
            problems = check()
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    parser.error("the lock is written by uv pip compile; only --check is supported")


if __name__ == "__main__":
    raise SystemExit(main())
