"""Pin the committed first-party corpus with per-file SHA-256 digests.

`build_first_party_corpus.py` needs the live setup-system repositories and a
release tag, so it cannot be the drift check: a hand edit inside
`first_party/v1/` used to be invisible to every gate. This manifest is the
local answer — `SHA256SUMS` lists the digest of every committed member, and
`--check` compares the closed set: a changed byte, a dropped member and an
unlisted file are each reported by name.
"""

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "packages" / "contracts" / "src" / "ai_stp_contracts" / "first_party" / "v1"
MANIFEST_NAME = "SHA256SUMS"


def render(root: Path) -> str:
    lines = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != MANIFEST_NAME:
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    return "\n".join(lines) + "\n"


def check(root: Path) -> list[str]:
    """Return named problems; an empty list means the corpus matches."""
    problems: list[str] = []
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return [f"missing corpus digest manifest: {manifest}"]
    recorded = {
        name: digest
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for digest, name in [line.split(None, 1)]
    }
    actual = {path.name for path in root.iterdir() if path.is_file()}
    for name in sorted(set(recorded) - actual):
        problems.append(f"corpus member missing: {root / name}")
    for name in sorted(actual - set(recorded) - {MANIFEST_NAME}):
        problems.append(f"corpus member has no recorded digest: {root / name}")
    for name in sorted(set(recorded) & actual):
        path = root / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != recorded[name]:
            problems.append(f"corpus member digest drifted: {path}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    if arguments.check:
        problems = check(CORPUS)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    CORPUS.joinpath(MANIFEST_NAME).write_text(render(CORPUS), encoding="utf-8")
    print(CORPUS / MANIFEST_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
