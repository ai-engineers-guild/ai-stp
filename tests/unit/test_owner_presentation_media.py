"""Owner presentation media contract (SPEC-035 upload + github + youtube)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_stp_contracts.owner import (
    COMPONENT_MEDIA_MAX_BYTES,
    OwnerPresentationMedia,
    validate_component_media_upload,
)


def test_validate_component_media_upload_allowlist() -> None:
    assert validate_component_media_upload(content_type="image/png", size_bytes=10) == "image"
    assert validate_component_media_upload(content_type="video/mp4", size_bytes=10) == "video"
    validate_component_media_upload(content_type="image/webp", size_bytes=COMPONENT_MEDIA_MAX_BYTES)
    with pytest.raises(ValueError, match="mime"):
        validate_component_media_upload(content_type="image/svg+xml", size_bytes=10)
    with pytest.raises(ValueError, match="size"):
        validate_component_media_upload(content_type="image/png", size_bytes=0)
    with pytest.raises(ValueError, match="size"):
        validate_component_media_upload(
            content_type="video/webm", size_bytes=COMPONENT_MEDIA_MAX_BYTES + 1
        )


def test_owner_presentation_media_accepts_upload_and_github() -> None:
    uploaded = OwnerPresentationMedia(
        kind="image",
        url="/v1/media/component/media_abc123",
        alt="Cover",
        caption="",
    )
    assert uploaded.url.startswith("/v1/media/component/")
    github = OwnerPresentationMedia(
        kind="video",
        url="https://raw.githubusercontent.com/org/repo/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/demo.mp4",
        alt="Demo",
    )
    assert github.kind == "video"
    youtube = OwnerPresentationMedia(kind="youtube", url="dQw4w9WgXcQ", alt="YT")
    assert youtube.url == "dQw4w9WgXcQ"


def test_owner_presentation_media_rejects_arbitrary_hosts() -> None:
    with pytest.raises(ValidationError):
        OwnerPresentationMedia(kind="image", url="https://example.com/x.png", alt="nope")
    with pytest.raises(ValidationError):
        OwnerPresentationMedia(kind="youtube", url="not-an-id", alt="nope")
