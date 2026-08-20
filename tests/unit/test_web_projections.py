"""Generated web projections stay bound to the Python contract source."""

from ai_stp_contracts import cli_copy
from ai_stp_contracts.web_projections import render_cli_copy, render_deep_link_corpus


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
