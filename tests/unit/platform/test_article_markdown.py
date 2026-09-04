"""Safe Markdown policy for article bodies (SPEC-054 REQ-5413)."""

from __future__ import annotations

import pytest

from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.markdown import validate_article_body

pytestmark = pytest.mark.platform


def _assert_invalid(source: str) -> None:
    with pytest.raises(ContentError) as error:
        validate_article_body(source)
    assert error.value.code == "AI_STP_CONTENT_INVALID"


def test_article_body_allows_https_fragment_and_illustration() -> None:
    source = "\n".join(
        [
            "See [docs](https://example.test/a) and [here](#keep).",
            "![boundary](/content/illustrations/trust-boundary.svg)",
        ]
    )
    assert validate_article_body(source) == source


@pytest.mark.parametrize(
    "source",
    [
        "@[youtube](https://www.youtube.com/watch?v=dQw4w9WgXcQ)",
        "@[vimeo](https://vimeo.com/12345678)",
    ],
)
def test_article_body_allows_supported_video_embed_links(source: str) -> None:
    assert validate_article_body(source) == source


def test_article_body_rejects_script_and_javascript_url() -> None:
    _assert_invalid("Hello <script>alert(1)</script>")
    _assert_invalid("[x](javascript:alert(1))")


def test_article_body_rejects_relative_non_illustration_link() -> None:
    _assert_invalid("[x](/tmp/secret)")


def test_article_body_rejects_unsupported_video_embed_host() -> None:
    _assert_invalid("@[youtube](https://evil.example/video/12345678)")


@pytest.mark.parametrize(
    "source",
    [
        'See [docs](https://example.test/a "Catalog docs") please.',
        "Jump [here](#) and back.",
        "![alt](/content/illustrations/trust-boundary.svg 'caption')",
        '<div class="note">plain angle brackets stay</div>',
        "conversation without an assignment",
        "https://example.test is plain text, not a markdown link",
    ],
)
def test_article_body_accepts_policy_safe_prose(source: str) -> None:
    assert validate_article_body(source) == source


@pytest.mark.parametrize(
    "source",
    [
        "Hello <script>alert(1)</script>",
        "Hello < script>alert(1)</script>",
        "x <iframe src=//evil></iframe>",
        "y <img src=x onerror=alert(1)>",
        "< svg xmlns='http://www.w3.org/2000/svg'>",
        "[x](javascript:alert(1))",
        "[x](data:text/html;base64,AAA)",
        "onclick=alert(1)",
        "onerror = alert(1)",
        "[x](/tmp/secret)",
        "[x](https://example.test@invalid.example/a)",
        "metadata: should still trip the data: substring",
    ],
)
def test_article_body_rejects_forbidden_markup_and_unsafe_urls(source: str) -> None:
    _assert_invalid(source)


@pytest.mark.parametrize(
    "kind",
    ["on", "open-bracket", "relative-open", "https-open", "fragment-open"],
)
def test_article_body_scans_quadratic_inputs_in_linear_time(kind: str) -> None:
    payloads = {
        "on": "on" * 20_000,
        "open-bracket": "[" * 40_000,
        "relative-open": "[](/" * 10_000,
        "https-open": "[](https://" * 5_000,
        "fragment-open": "[](#" * 10_000,
    }
    source = payloads[kind]
    assert validate_article_body(source) == source
