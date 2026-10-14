"""Maintained public guidance must not promote retired CLI entrypoints."""

import re
from pathlib import Path


def test_user_docs_do_not_start_retired_intents_or_install_python_cli() -> None:
    stale = []
    for path in Path("docs-user-facing").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if (
            re.search(
                r"ai-stp task start --intent (initialize|account|publish|change|switch|inspect|technology)\b",
                text,
            )
            or "uv tool install ai-stp-cli" in text
        ):
            stale.append(str(path))
    assert not stale
