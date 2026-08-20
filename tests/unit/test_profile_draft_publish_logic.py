"""Draft must not alter public projection until publish (SPEC-028 REQ-2803)."""

from __future__ import annotations

from ai_stp_contracts.public_profile import (
    ProfileFields,
    ProfileLink,
    content_digest,
    is_empty_profile,
    public_projection,
)


def test_draft_and_published_are_independent_projections() -> None:
    published = ProfileFields(
        display_name="Published Name",
        bio="live",
        links=[ProfileLink(label="Site", url="https://example.com/live")],
    )
    draft = ProfileFields(
        display_name="Draft Name",
        bio="wip",
        links=[ProfileLink(label="Site", url="https://example.com/wip")],
    )
    public_before = public_projection(
        account_id="account_1",
        fields=published,
        avatar_public_url=None,
    )
    # Saving draft only produces a different digest; public projection still uses published.
    assert content_digest(draft) != content_digest(published)
    public_after_draft_save = public_projection(
        account_id="account_1",
        fields=published,
        avatar_public_url=None,
    )
    assert public_after_draft_save == public_before
    assert public_after_draft_save["display_name"] == "Published Name"

    published_after = public_projection(
        account_id="account_1",
        fields=draft,
        avatar_public_url="/media/avatars/x",
    )
    assert published_after["display_name"] == "Draft Name"
    assert published_after["avatar_url"] == "/media/avatars/x"
    assert "email" not in published_after


def test_empty_publish_clears_public_card() -> None:
    assert is_empty_profile(ProfileFields())
    assert not is_empty_profile(ProfileFields(display_name="X"))
