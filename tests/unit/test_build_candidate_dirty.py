"""A dirty worktree is characterization, never release evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
from release_scripts.build_candidate import CandidateError, build_candidate


def test_dirty_tree_is_refused_without_allow_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(*arguments: str) -> str:
        if arguments[:2] == ("status", "--porcelain"):
            return " M apps/cli/src/ai_stp_cli/application/qualify.py"
        if arguments[:2] == ("rev-parse", "HEAD"):
            return "a" * 40
        if arguments[:2] == ("show", "-s"):
            return "1710000000"
        raise AssertionError(arguments)

    monkeypatch.setattr("release_scripts.build_candidate._git", fake_git)
    with pytest.raises(CandidateError, match="clean worktree"):
        build_candidate(
            tmp_path / "release-candidate",
            allow_dirty=False,
            expected_version=None,
            require_tag=False,
            replace=False,
        )
