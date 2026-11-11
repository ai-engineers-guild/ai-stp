"""Validate the official Go database archive before publishing any data."""

from __future__ import annotations

import json
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.platform
_SCRIPT = Path(__file__).resolve().parents[3] / "scripts/safety/prepare_go_db.py"
_INDEXES = {
    "index/db.json": '{"modified":"2026-01-01T00:00:00Z"}',
    "index/modules.json": "[]",
    "index/vulns.json": "[]",
}


def _run(
    tmp_path: Path, entries: list[tuple[str, str]], *, max_bytes: int = 65536, max_files: int = 100
) -> tuple[subprocess.CompletedProcess[str], Path]:
    archive = tmp_path / "database.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, data in entries:
                bundle.writestr(name, data)
    destination = tmp_path / "prepared"
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            str(archive),
            str(destination),
            str(max_bytes),
            str(max_files),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    return result, destination


def test_official_layout_preserves_record_bytes_and_marks_success(tmp_path: Path) -> None:
    record = '{"id":"GO-2026-999999","summary":"controlled fixture"}'
    result, destination = _run(tmp_path, [*_INDEXES.items(), ("ID/GO-2026-999999.json", record)])
    assert result.returncode == 0, result.stderr
    assert (destination / "ID/GO-2026-999999.json").read_text() == record
    assert (destination / ".ai_stp_osv_refreshed_at").is_file()
    assert "archive_sha256=" in (destination / "STATUS.txt").read_text()


@pytest.mark.parametrize(
    "fault",
    [
        "missing_index",
        "traversal",
        "duplicate",
        "wrong_identity",
        "invalid_json",
        "invalid_index",
        "byte_limit",
        "file_limit",
        "invalid_limit",
    ],
)
def test_invalid_bundle_never_becomes_fresh(tmp_path: Path, fault: str) -> None:
    entries = list(_INDEXES.items())
    max_bytes, max_files = 65536, 100
    if fault == "missing_index":
        entries.pop()
    elif fault == "traversal":
        entries.append(("../escaped.json", "{}"))
    elif fault == "duplicate":
        entries.append(entries[0])
    elif fault == "wrong_identity":
        entries.append(("ID/GO-2026-999999.json", '{"id":"GO-2026-1"}'))
    elif fault == "invalid_json":
        entries.append(("ID/GO-2026-999999.json", "{"))
    elif fault == "invalid_index":
        entries[1] = ("index/modules.json", json.dumps({}))
    elif fault == "byte_limit":
        max_bytes = 1
    elif fault == "file_limit":
        max_files = 1
    else:
        max_files = 0
    result, destination = _run(tmp_path, entries, max_bytes=max_bytes, max_files=max_files)
    assert result.returncode != 0
    assert not (destination / ".ai_stp_osv_refreshed_at").exists()
    assert not (tmp_path / "escaped.json").exists()
