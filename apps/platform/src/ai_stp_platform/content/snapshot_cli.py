"""Bake a repository article snapshot at image build (SPEC-054)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_stp_foundation.canonical import canonize
from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.snapshot import build_repository_snapshot, snapshot_as_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a content-hub snapshot.")
    parser.add_argument("--hub", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = build_repository_snapshot(args.hub, commit=args.commit)
    except ContentError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    args.out.write_bytes(canonize(dict(snapshot_as_json(snapshot))))
    sys.stdout.write(
        f"snapshot_digest={snapshot.snapshot_digest} commit={snapshot.commit} "
        f"entries={len(snapshot.entries)}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
