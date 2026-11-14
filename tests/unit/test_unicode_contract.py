"""Every Python NFC/NFKC owner normalizes with the CLI's Unicode version (#1481)."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_foundation import unicodedata

ROOT = Path(__file__).resolve().parents[2]


def test_python_owners_use_the_contract_unicode_version() -> None:
    assert unicodedata.unidata_version == unicodedata.CONTRACT_VERSION == "18.0.0"
    cargo = (ROOT / "apps/cli/Cargo.toml").read_text(encoding="utf-8")
    pinned = re.search(r'^unicode-normalization = "=([0-9.]+)"$', cargo, re.M)
    # unicode-normalization 0.1.26 carries the Unicode 18.0.0 tables.
    assert pinned is not None and pinned.group(1) == "0.1.26"


def test_no_source_owner_imports_the_interpreter_unicode_database() -> None:
    pattern = re.compile(r"^\s*(import unicodedata\b|from unicodedata import)", re.M)
    offenders = [
        str(path.relative_to(ROOT))
        for path in [*ROOT.glob("packages/*/src/**/*.py"), *ROOT.glob("apps/*/src/**/*.py")]
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
