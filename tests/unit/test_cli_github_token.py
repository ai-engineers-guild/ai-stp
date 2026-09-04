"""GitHub API bearer is read from the environment and never interpolated."""

import pytest

from ai_stp_cli.github_token import github_api_token


def test_github_api_token_prefers_github_token_over_gh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "github_pat_test_api")
    monkeypatch.setenv("GH_TOKEN", "gho_should_not_win")
    assert github_api_token() == "github_pat_test_api"


def test_github_api_token_is_absent_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert github_api_token() is None
