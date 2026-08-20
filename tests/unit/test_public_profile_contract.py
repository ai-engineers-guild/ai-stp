"""Pure public-profile validation and projection (SPEC-028)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_stp_contracts.public_profile import (
    BIO_MAX,
    DISPLAY_NAME_MAX,
    LINK_LABEL_MAX,
    LINKS_MAX,
    ProfileFields,
    ProfileLink,
    content_digest,
    is_empty_profile,
    public_projection,
    validate_avatar_upload,
)
from ai_stp_contracts.safe_markdown import render_description


def test_field_limits_and_https_links() -> None:
    fields = ProfileFields(
        display_name="Danil",
        bio="x" * BIO_MAX,
        links=[ProfileLink(label="GitHub", url="https://github.com/ai-stp")],
    )
    assert fields.display_name == "Danil"
    assert len(fields.bio or "") == BIO_MAX
    digest = content_digest(fields)
    assert digest.startswith("sha256:")
    assert content_digest(fields) == digest


def test_display_name_and_bio_bounds() -> None:
    assert ProfileFields(display_name="   ").display_name is None
    assert ProfileFields(bio=None).bio is None
    with pytest.raises(ValidationError):
        ProfileFields(display_name="x" * (DISPLAY_NAME_MAX + 1))
    with pytest.raises(ValidationError):
        ProfileFields(bio="y" * (BIO_MAX + 1))
    with pytest.raises(ValidationError):
        ProfileFields(bio="hello <b>x</b>")
    with pytest.raises(ValidationError):
        ProfileFields(bio="click javascript:alert(1)")
    # Limited Markdown is allowed (bold / code / links).
    ok = ProfileFields(bio="has `code` and **bold** and [x](https://example.com)")
    assert ok.bio is not None
    assert "`code`" in ok.bio


def test_link_rules() -> None:
    with pytest.raises(ValidationError):
        ProfileLink(label="x", url="http://example.com")
    with pytest.raises(ValidationError):
        ProfileLink(label="x", url="https://user:pass@example.com/a")
    with pytest.raises(ValidationError):
        ProfileLink(label="x", url="https://")
    with pytest.raises(ValidationError):
        ProfileLink(label="", url="https://example.com")
    with pytest.raises(ValidationError):
        ProfileLink(label="x" * (LINK_LABEL_MAX + 1), url="https://example.com")
    ok = ProfileLink(label="Docs", url="https://Example.COM/path/")
    assert ok.url.startswith("https://")
    queried = ProfileLink(label="Search", url="https://Example.COM?q=value#ignored")
    assert queried.url == "https://example.com?q=value"


def test_duplicate_and_max_links() -> None:
    with pytest.raises(ValidationError):
        ProfileFields(
            links=[
                ProfileLink(label="A", url="https://example.com/a"),
                ProfileLink(label="B", url="https://example.com/a"),
            ]
        )
    many = [ProfileLink(label=f"L{i}", url=f"https://example.com/{i}") for i in range(LINKS_MAX)]
    ProfileFields(links=many)
    with pytest.raises(ValidationError):
        ProfileFields(
            links=[
                *many,
                ProfileLink(label="extra", url="https://example.com/extra"),
            ]
        )


def test_public_projection_allowlist_and_empty() -> None:
    fields = ProfileFields(display_name="N", bio="b", links=[])
    body = public_projection(
        account_id="account_1",
        fields=fields,
        avatar_public_url="https://cdn.example/a.png",
    )
    assert set(body.keys()) == {
        "schema_version",
        "kind",
        "account_id",
        "display_name",
        "bio",
        "links",
        "avatar_url",
        "author_verified",
    }
    assert "email" not in body
    assert "object_key" not in body
    assert not is_empty_profile(fields)
    assert is_empty_profile(ProfileFields())
    assert is_empty_profile(ProfileFields(bio=""))


def test_avatar_upload_rules() -> None:
    validate_avatar_upload(content_type="image/png", size_bytes=1024)
    validate_avatar_upload(content_type="image/jpeg", size_bytes=1)
    validate_avatar_upload(content_type="image/webp", size_bytes=5 * 1024 * 1024)
    with pytest.raises(ValueError):
        validate_avatar_upload(content_type="image/gif", size_bytes=10)
    with pytest.raises(ValueError):
        validate_avatar_upload(content_type="image/png", size_bytes=0)
    with pytest.raises(ValueError):
        validate_avatar_upload(content_type="image/png", size_bytes=6 * 1024 * 1024)


def test_safe_markdown_renders_table_emoji_and_annotated_link() -> None:
    rendered = render_description(
        "## Matrix 🚀\n\n| Harness | State |\n| --- | --- |\n| Codex | Ready |\n\n"
        '[Docs](https://example.com/docs "Reference")'
    )

    assert "<table>" in rendered.html
    assert "<th>Harness</th>" in rendered.html
    assert "🚀" in rendered.html
    assert 'title="Reference"' in rendered.html


def test_digest_changes_when_field_changes() -> None:
    a = ProfileFields(display_name="A")
    b = ProfileFields(display_name="B")
    assert content_digest(a) != content_digest(b)
