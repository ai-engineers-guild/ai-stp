"""An SDK upgrade cannot silently retain packaging assets qualified for another SDK."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from release_scripts.desktop_tools import ROOT, check


def test_packaging_tools_match_the_selected_desktop_sdk() -> None:
    check()


def test_upgrading_the_cli_requires_explicit_tool_qualification(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / "apps/desktop").mkdir(parents=True)
    (tmp_path / ".github/tauri-tools.json").write_bytes(
        (ROOT / ".github/tauri-tools.json").read_bytes()
    )
    package = json.loads((ROOT / "apps/desktop/package.json").read_text())
    package["devDependencies"]["@tauri-apps/cli"] = "999.0.0"
    (tmp_path / "apps/desktop/package.json").write_text(json.dumps(package))
    with pytest.raises(ValueError, match="exact qualified packaging SDK"):
        check(tmp_path)
