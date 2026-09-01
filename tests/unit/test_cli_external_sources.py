"""External source syntax stays separate from exact provenance."""

from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import external_sources

SHA = "a" * 40


@pytest.mark.parametrize(
    ("value", "kind", "subpath"),
    [
        ("@author/skill@1.2.0", "published", None),
        ("gh:owner/repo@review", "github", None),
        ("owner/repo/path/to/skill", "github", "path/to/skill"),
        (f"https://github.com/owner/repo/tree/{SHA}/skills/a", "github", "skills/a"),
        ("col:owner/team", "collection", None),
        ("https://askill.sh/c/owner/team", "collection", None),
        ("./skills/a", "local", None),
    ],
)
def test_supported_source_intents_are_structured_without_trust(
    tmp_path: Path, value: str, kind: str, subpath: str | None
) -> None:
    result = external_sources.parse(value, cwd=tmp_path)
    assert result.kind == kind
    assert result.subpath == subpath


def test_only_a_full_commit_promotes_github_intent_to_exact(tmp_path: Path) -> None:
    intent = external_sources.parse("owner/repo/skills/a", cwd=tmp_path)
    exact = external_sources.resolve_exact(intent, commit=SHA)
    assert exact.kind == "github/exact"
    assert exact.ref == SHA
    assert exact.repository == "https://github.com/owner/repo"

    for revision in ("main", "v1.0.0", "a" * 39, "A" * 40):
        with pytest.raises(CliFailure) as caught:
            external_sources.resolve_exact(intent, commit=revision)
        assert caught.value.code == "AI_STP_VALIDATION_ERROR"


@pytest.mark.parametrize(
    "value",
    [
        "https://user:token@github.com/owner/repo",
        "https://github.com/owner/repo/tree/main/../secret",
        "https://github.com/owner/repo/issues/1",
        "owner/repo/a/../../secret",
        "git@example.com:owner/repo.git",
        "",
    ],
)
def test_ambiguous_or_unsafe_sources_fail_closed(tmp_path: Path, value: str) -> None:
    with pytest.raises(CliFailure) as caught:
        external_sources.parse(value, cwd=tmp_path)
    assert caught.value.code == "AI_STP_VALIDATION_ERROR"


def test_non_github_intents_cannot_be_promoted(tmp_path: Path) -> None:
    for value in ("./local", "@author/skill", "col:owner/team"):
        with pytest.raises(CliFailure) as caught:
            external_sources.resolve_exact(external_sources.parse(value, cwd=tmp_path), commit=SHA)
        assert caught.value.code == "AI_STP_VALIDATION_ERROR"
