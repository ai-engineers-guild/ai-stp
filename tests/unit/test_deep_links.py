"""Shared deep-link grammar and corpus (SPEC-030)."""

import json
from importlib.resources import files
from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_contracts.deep_links import (
    DeepLinkTarget,
    build_deep_link,
    parse_deep_link,
)


def _corpus() -> dict[str, object]:
    source = files("ai_stp_contracts").joinpath("fixtures/deep-links/v1.json")
    return cast(dict[str, object], json.loads(source.read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", cast(list[dict[str, object]], _corpus()["positive"]))
def test_shared_corpus_round_trips_exact_url_and_cli_argv(case: dict[str, object]) -> None:
    target = DeepLinkTarget.model_validate(case["target"])
    view = build_deep_link(str(case["platform_base"]), target)

    assert view.web_url == case["web_url"]
    assert view.cli_argv == case["cli_argv"]
    assert view.cli_command == " ".join(view.cli_argv)
    assert parse_deep_link(str(case["platform_base"]), view.web_url) == target


@pytest.mark.parametrize("target", cast(list[dict[str, object]], _corpus()["invalid_targets"]))
def test_invalid_target_combinations_fail_closed(target: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DeepLinkTarget.model_validate(target)


@pytest.mark.parametrize("web_url", cast(list[str], _corpus()["invalid_urls"]))
def test_invalid_or_foreign_urls_never_become_cli_references(web_url: str) -> None:
    with pytest.raises(ValueError):
        parse_deep_link("https://example.test", web_url)


@pytest.mark.parametrize(
    "base",
    [
        "https://user@example.test",
        "https://example.test?token=secret",
        "https://example.test/#fragment",
        "https://example.test/%2e%2e",
        "https://example.test/../other",
    ],
)
def test_platform_base_carries_no_ambient_authority_or_ambiguous_path(base: str) -> None:
    target = DeepLinkTarget(
        kind="publisher",
        stable_id="account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    )
    with pytest.raises(ValueError):
        build_deep_link(base, target)


def test_report_intent_is_only_the_fixed_fragment_of_an_exact_version() -> None:
    target = DeepLinkTarget(
        kind="component",
        stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        version="9.0",
        locale="en",
        intent="report",
    )
    view = build_deep_link("https://example.test", target)
    assert view.web_url.endswith("/versions/9.0#report")
    assert parse_deep_link("https://example.test", view.web_url).intent == "report"


def test_the_corpus_is_explicitly_versioned() -> None:
    assert _corpus()["schema_version"] == 1
