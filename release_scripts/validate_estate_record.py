"""Offline validator for `ai-stp-estate-release/1`."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ai_stp_contracts.estate_release import EstateRelease, computed_verdict


def validate(path: Path, *, artifacts: Path | None = None) -> list[str]:
    """Return problems. Empty means the record is well-formed and honest."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"the estate release record is not valid JSON: {error}"]
    try:
        record = EstateRelease.model_validate(payload)
    except ValidationError as error:
        return [f"the estate release record does not satisfy ai-stp-estate-release/1: {error}"]
    problems: list[str] = []
    actual = computed_verdict(record)
    if actual != record.verdict:
        problems.append(
            "the estate release verdict is not supported by its evidence: "
            f"stored {record.verdict}, computed {actual}"
        )
    problems.extend(_artifact_problems(record, beside=path.parent, artifacts=artifacts))
    return problems


def _named_files(record: EstateRelease) -> list[tuple[str, str]]:
    named: list[tuple[str, str]] = []
    for item in record.distributions:
        named.append((item.filename, item.digest))
    for provider in record.providers:
        for item in provider.native_artifacts:
            named.append((item.filename, item.digest))
        for item in provider.wheels:
            named.append((item.filename, item.digest))
    return named


def _locate(filename: str, *, beside: Path, artifacts: Path | None) -> Path | None:
    candidates = [beside / filename]
    if artifacts is not None:
        candidates.append(artifacts / filename)
        candidates.append(artifacts / Path(filename).name)
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None


def _file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _artifact_problems(record: EstateRelease, *, beside: Path, artifacts: Path | None) -> list[str]:
    named = _named_files(record)
    if not named:
        return []
    required = artifacts is not None
    if not required and not any(
        (beside / filename).is_file() and not (beside / filename).is_symlink()
        for filename, _digest in named
    ):
        return []
    problems: list[str] = []
    seen: set[str] = set()
    for filename, digest in named:
        if filename in seen:
            continue
        seen.add(filename)
        held = _locate(filename, beside=beside, artifacts=artifacts)
        if held is None:
            if required:
                problems.append(f"missing artifact file {filename}")
            continue
        observed = _file_digest(held)
        if observed != digest:
            problems.append(f"{filename} digest is {observed}, record claims {digest}")
    return problems


def main(argv: list[str] | Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--artifacts",
        type=Path,
        help="Directory of named distribution and provider artifact files.",
    )
    args = parser.parse_args(argv)
    problems = validate(args.path, artifacts=args.artifacts)
    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
