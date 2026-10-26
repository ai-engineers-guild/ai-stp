"""Packaging retry policy with owned fake commands; no desktop build or disk image."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/build-desktop-bundles.sh"
FAKE_BUN = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${FIXTURE_CALLS}"
if [[ "$3" == build ]]; then
  if [[ "${FIXTURE_CASE}" == compile ]]; then exit 42; fi
  exit 0
fi
count=0
if [[ -f "${FIXTURE_COUNT}" ]]; then read -r count < "${FIXTURE_COUNT}"; fi
count=$((count + 1))
printf '%s\n' "${count}" > "${FIXTURE_COUNT}"
case "${FIXTURE_CASE}" in
  once) if [[ "${count}" -gt 1 ]]; then exit 0; fi ;;
  success) exit 0 ;;
  permission) echo 'hdiutil: create failed - Permission denied'; exit 23 ;;
  detach) echo 'hdiutil: detach failed - Resource busy'; exit 16 ;;
esac
echo 'failed to bundle project: hdiutil: create failed - Resource busy'
exit 1
"""


@pytest.mark.parametrize(
    ("runner", "case", "status", "bundles", "delays"),
    [
        ("macOS", "success", 0, 1, []),
        ("macOS", "once", 0, 2, ["2"]),
        ("macOS", "busy", 1, 3, ["2", "4"]),
        ("macOS", "permission", 23, 1, []),
        ("macOS", "detach", 16, 1, []),
        ("macOS", "compile", 42, 0, []),
        ("Linux", "success", 0, 0, []),
        ("Windows", "success", 0, 0, []),
    ],
)
def test_desktop_packaging_retries_only_busy_create_without_rebuilding(
    tmp_path: Path, runner: str, case: str, status: int, bundles: int, delays: list[str]
) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    for name, content in (
        ("bun", FAKE_BUN),
        ("sleep", '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "${FIXTURE_DELAYS}"\n'),
    ):
        path = bin_directory / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    calls, waits = tmp_path / "calls", tmp_path / "delays"
    canary = tmp_path / "unowned"
    canary.write_bytes(b"preserve fixture data\n")
    result = subprocess.run(
        [bash, str(SCRIPT)],
        env={
            **os.environ,
            "PATH": str(bin_directory) + os.pathsep + os.environ["PATH"],
            "RUNNER_OS": runner,
            "RUNNER_TEMP": str(tmp_path),
            "FIXTURE_CASE": case,
            "FIXTURE_CALLS": str(calls),
            "FIXTURE_COUNT": str(tmp_path / "count"),
            "FIXTURE_DELAYS": str(waits),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == status, (result.stdout, result.stderr)
    expected = ["x tauri build --no-bundle"] if runner == "macOS" else ["x tauri build"]
    assert calls.read_text().splitlines() == expected + ["x tauri bundle"] * bundles
    assert (waits.read_text().splitlines() if waits.exists() else []) == delays
    assert not list(tmp_path.glob("ai-stp-dmg.*"))
    assert canary.read_bytes() == b"preserve fixture data\n"
