"""Commit identity is owned by the current user's global Git config (SPEC-049)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_agents_requires_dynamic_global_identity_and_forbids_overrides() -> None:
    assert "git config --global --get user.name" in AGENTS
    assert "git config --global --get user.email" in AGENTS
    assert "--author" in AGENTS
    assert "не передаёт `--author`" in AGENTS or "does not pass `--author`" in AGENTS
    assert "Co-authored-by" in AGENTS
    assert "не меняет `user.name`" in AGENTS


def test_repository_files_do_not_hardcode_a_commit_author() -> None:
    forbidden = (
        "Co-authored-by: Claude",
        "Generated-by: Claude",
        "Co-authored-by: Grok",
        "Generated-by: Grok",
    )
    scanned = [
        ROOT / "AGENTS.md",
        ROOT / "justfile",
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "specs").rglob("*.md")),
    ]
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{path} contains {marker}"
