"""Public document publish/read allowlist (SPEC-031) using pure markdown path."""

from __future__ import annotations

from ai_stp_api.slices.documents.service import KIND_BY_SLUG
from ai_stp_contracts.safe_markdown import render_description, source_digest


def test_policy_slugs_map_to_kinds() -> None:
    assert KIND_BY_SLUG["privacy"] == "privacy"
    assert KIND_BY_SLUG["licensing"] == "author_content_and_license"


def test_published_document_body_uses_safe_html() -> None:
    source = "## Rules\n\nAuthors keep rights. [Policy](https://example.com/p)"
    rendered = render_description(source)
    assert 'rel="noopener noreferrer"' in rendered.html
    assert source_digest(source) == rendered.source_digest
    assert "<script" not in rendered.html.lower()
