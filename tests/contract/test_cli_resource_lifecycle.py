"""Repeated in-process CLI reads close every SQLite connection they open."""

from __future__ import annotations

import gc
import json
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli import app


def _descriptor_directory() -> Path | None:
    for candidate in (Path("/proc/self/fd"), Path("/dev/fd")):
        if candidate.is_dir():
            return candidate
    return None


def _descriptor_count(directory: Path) -> int:
    # Materialise the iterator before returning so the directory handle used by
    # the enumeration itself is already closed when the number is compared.
    return len(list(directory.iterdir()))


def _invoke(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert app.main([*argv, "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_resource_gate_promotes_both_warning_forms() -> None:
    recipe = Path("justfile").read_text(encoding="utf-8")
    assert "back-resource:" in recipe
    assert "-W error::ResourceWarning" in recipe
    assert "-W error::pytest.PytestUnraisableExceptionWarning" in recipe
    assert "back-check: back-static back-test back-resource" in recipe


def test_repeated_in_process_reads_do_not_accumulate_descriptors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = _descriptor_directory()
    if directory is None:  # pragma: no cover - Ubuntu and macOS expose one
        pytest.skip("the host has no process descriptor directory")

    created = _invoke(["passport", "developer", "init"], capsys)
    data = cast(dict[str, object], created["data"])
    stable_id = str(data["stable_id"])

    # Warm every path before the baseline so lazy imports and Click construction
    # are not mistaken for a resource leak.
    commands = (
        ["passport", "developer", "show"],
        ["sync", "preview", "--id", stable_id],
        ["doctor"],
    )
    for command in commands:
        _invoke(command, capsys)
    gc.collect()
    baseline = _descriptor_count(directory)

    for _iteration in range(25):
        for command in commands:
            _invoke(command, capsys)
    gc.collect()

    assert _descriptor_count(directory) == baseline
