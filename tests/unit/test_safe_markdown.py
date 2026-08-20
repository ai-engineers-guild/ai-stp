"""One safe-Markdown contract for passports and every future renderer."""

import json
from importlib.resources import files
from typing import Any, cast

import pytest

from ai_stp_passports import (
    MAX_DESCRIPTION_BYTES,
    MAX_DESCRIPTION_LINES,
    MAX_EXCERPT_CODEPOINTS,
    MarkdownPolicyError,
    project_safe_markdown,
)


def _corpus() -> dict[str, Any]:
    path = files("ai_stp_passports.fixtures").joinpath("safe-markdown-v1.json")
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", _corpus()["accepted"], ids=lambda case: case["id"])
def test_shared_corpus_has_exact_safe_projections(case: dict[str, str]) -> None:
    projection = project_safe_markdown(case["source"])
    assert projection.description_format == _corpus()["description_format"]
    assert projection.renderer_version == _corpus()["renderer_version"]
    assert projection.html == case["html"]
    assert projection.excerpt == case["excerpt"]


@pytest.mark.parametrize("case", _corpus()["rejected"], ids=lambda case: case["id"])
def test_shared_malicious_corpus_fails_closed(case: dict[str, str]) -> None:
    with pytest.raises(MarkdownPolicyError) as caught:
        project_safe_markdown(case["source"])
    assert caught.value.code == case["code"]


def test_limits_are_applied_before_rendering() -> None:
    with pytest.raises(MarkdownPolicyError) as oversized:
        project_safe_markdown("я" * (MAX_DESCRIPTION_BYTES // 2 + 1))
    assert oversized.value.code == "too_large"

    with pytest.raises(MarkdownPolicyError) as too_many_lines:
        project_safe_markdown("x\n" * MAX_DESCRIPTION_LINES)
    assert too_many_lines.value.code == "too_many_lines"


def test_excerpt_boundary_is_deterministic_in_unicode_code_points() -> None:
    exact = "я" * MAX_EXCERPT_CODEPOINTS
    assert project_safe_markdown(exact).excerpt == exact
    assert project_safe_markdown(f"{exact}я").excerpt == f"{'я' * 239}…"


def test_unknown_renderer_never_downgrades() -> None:
    with pytest.raises(MarkdownPolicyError) as caught:
        project_safe_markdown("text", renderer_version="safe_markdown_v2")
    assert caught.value.code == "unsupported_renderer"
