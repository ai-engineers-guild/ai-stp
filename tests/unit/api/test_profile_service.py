# pyright: reportPrivateUsage=false
"""Public profile projection compatibility tests."""

from ai_stp_api.slices.profile.service import _fields_from_revision
from ai_stp_platform.models import ProfileRevision


def test_legacy_published_profile_keeps_identity_and_avatar_when_bio_is_rejected() -> None:
    revision = ProfileRevision(
        id="prevision_legacy",
        account_id="account_legacy",
        lifecycle="published",
        display_name="Artem Letyushev",
        bio="# Legacy markdown bio with [a link](https://example.com)",
        links=[{"label": "Site", "url": "https://example.com"}],
        avatar_asset_id="avatar_legacy",
        content_digest="sha256:" + ("0" * 64),
    )

    fields = _fields_from_revision(revision)

    assert fields.display_name == "Artem Letyushev"
    assert fields.bio is None
    assert fields.links[0].url == "https://example.com"
    assert fields.avatar_asset_id == "avatar_legacy"
