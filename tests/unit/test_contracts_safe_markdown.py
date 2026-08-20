"""Safe markdown pipeline (SPEC-029) — deep negative/positive corpus."""

from __future__ import annotations

import pytest

from ai_stp_contracts.safe_markdown import (
    DESCRIPTION_MAX_BYTES,
    EXCERPT_MAX_CHARS,
    RENDERER_VERSION,
    MarkdownValidationError,
    excerpt_from_source,
    render_description,
    source_digest,
    validate_description,
)


@pytest.mark.parametrize(
    "source",
    [
        "hi <script>alert(1)</script>",
        "x <iframe src=//evil></iframe>",
        "y <img src=x onerror=alert(1)>",
        "[x](javascript:alert(1))",
        "[x](data:text/html;base64,AAA)",
        "onclick=alert(1)",
        "a" * (DESCRIPTION_MAX_BYTES + 10),
        "   \n\n  ",
    ],
)
def test_rejects_malicious_or_empty_markdown(source: str) -> None:
    with pytest.raises(MarkdownValidationError):
        validate_description(source)


def test_allows_fragment_links_and_https() -> None:
    source = "See [here](#section) and [docs](https://example.com/a)."
    rendered = render_description(source)
    assert (
        'href="#section"' in rendered.html
        or "href=&#x27;#section&#x27;" in rendered.html
        or "#section" in rendered.html
    )
    assert 'rel="noopener noreferrer"' in rendered.html
    assert "https://example.com/a" in rendered.html


def test_render_lists_headings_code_emphasis() -> None:
    source = """## Title

Paragraph with **bold** and *em* and `code`.

- one
- two

1. first
2. second

```
ls -la
```
"""
    rendered = render_description(source)
    assert "<strong>bold</strong>" in rendered.html
    assert "<em>em</em>" in rendered.html
    assert "<code>code</code>" in rendered.html
    assert "<ul>" in rendered.html
    assert "<ol>" in rendered.html
    assert "<pre><code>" in rendered.html
    assert rendered.renderer_version == RENDERER_VERSION
    assert "<script" not in rendered.html.lower()


def test_excerpt_deterministic_and_bounded() -> None:
    source = "word " * 200
    a = excerpt_from_source(source)
    b = excerpt_from_source(source)
    assert a == b
    assert len(a) <= EXCERPT_MAX_CHARS
    assert a.endswith("…") or len(a) < EXCERPT_MAX_CHARS


def test_digest_changes_with_source_bytes() -> None:
    assert source_digest("a") != source_digest("b")
    rendered = render_description("hello world")
    assert rendered.source_digest == source_digest("hello world")


def test_credential_bearing_url_rejected() -> None:
    with pytest.raises(MarkdownValidationError):
        validate_description("[x](https://user:pass@example.com/a)")


def test_table_emoji_and_annotated_link_render_without_losing_metadata() -> None:
    rendered = render_description(
        "# Features 🚀\n\n| Capability | Status |\n| :--- | ---: |\n"
        '| Search | ✅ |\n\n[Reference](https://example.com/docs "Catalog docs")'
    )

    assert "<table>" in rendered.html
    assert "<th>Capability</th>" in rendered.html
    assert "🚀" in rendered.html and "✅" in rendered.html
    assert 'title="Catalog docs"' in rendered.html


def test_plain_text_is_escaped_and_multiline_text_becomes_one_paragraph() -> None:
    rendered = render_description("first < second\nthird & fourth")

    assert rendered.html == "<p>first &lt; second third &amp; fourth</p>"


def test_excerpt_strips_fences_links_inline_code_and_markers() -> None:
    source = "```txt\ncode\n```\n\nSee [docs](https://example.com) and `value` **now**."

    assert excerpt_from_source(source) == "code See docs and value now ."
