"""Offline validator for `ai-stp-estate-release/1`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from ai_stp_contracts.estate_release import EstateRelease, computed_verdict


def validate(path: Path) -> list[str]:
    """Return problems. Empty means the record is well-formed and honest."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"the estate release record is not valid JSON: {error}"]
    try:
        record = EstateRelease.model_validate(payload)
    except ValidationError as error:
        return [f"the estate release record does not satisfy ai-stp-estate-release/1: {error}"]
    actual = computed_verdict(record)
    if actual != record.verdict:
        return [
            "the estate release verdict is not supported by its evidence: "
            f"stored {record.verdict}, computed {actual}"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    problems = validate(args.path)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
