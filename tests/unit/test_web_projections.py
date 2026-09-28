"""Generated web projections stay bound to the Python contract source."""

from pathlib import Path

from ai_stp_contracts import cli_copy
from ai_stp_contracts.web_projections import (
    check,
    render_all,
    render_cli_copy,
    render_deep_link_corpus,
)


def test_cli_copy_projection_contains_the_canonical_distribution() -> None:
    rendered = render_cli_copy()
    assert cli_copy.DISTRIBUTION in rendered
    assert cli_copy.INSTALL_CLI in rendered
    assert cli_copy.REGISTRY_SHOW in rendered
    assert "ai-stp use" not in rendered
    assert "@{version}" not in rendered


def test_deep_link_projection_embeds_the_packaged_corpus() -> None:
    rendered = render_deep_link_corpus()
    assert "component-object-default-locale" in rendered
    assert "deep-link URL must carry no credentials" not in rendered
    assert "DEEP_LINK_CORPUS" in rendered


def test_check_rejects_an_unlisted_file_in_the_target(tmp_path: Path) -> None:
    """An orphaned `.ts` beside the projections must not read as one of them."""
    for name, content in render_all().items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "orphan.ts").write_text("// stray\n", encoding="utf-8")

    problems = check(tmp_path)

    assert any("orphan.ts" in problem for problem in problems)


def test_check_passes_on_the_exact_generated_set(tmp_path: Path) -> None:
    """The control that proves the gate discriminates: the exact set is clean."""
    for name, content in render_all().items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    assert check(tmp_path) == []
