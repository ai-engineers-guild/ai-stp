"""Safe Markdown policy for article bodies (SPEC-054 REQ-5413)."""

from __future__ import annotations

import pytest

from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.markdown import validate_article_body

pytestmark = pytest.mark.platform


def test_article_body_allows_https_fragment_and_illustration() -> None:
    source = "\n".join(
        [
            "See [docs](https://example.test/a) and [here](#keep).",
            "![boundary](/content/illustrations/trust-boundary.svg)",
        ]
    )
    assert validate_article_body(source) == source


def test_article_body_rejects_script_and_javascript_url() -> None:
    with pytest.raises(ContentError) as error:
        validate_article_body("Hello <script>alert(1)</script>")
    assert error.value.code == "AI_STP_CONTENT_INVALID"
    with pytest.raises(ContentError) as error:
        validate_article_body("[x](javascript:alert(1))")
    assert error.value.code == "AI_STP_CONTENT_INVALID"


def test_article_body_rejects_relative_non_illustration_link() -> None:
    with pytest.raises(ContentError) as error:
        validate_article_body("[x](/tmp/secret)")
    assert error.value.code == "AI_STP_CONTENT_INVALID"
