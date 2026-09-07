"""The avatar boundary decodes pixels and never forwards input metadata."""

from io import BytesIO

import pytest
from PIL import Image
from tests.support.images import image_bytes

from ai_stp_api.errors import ApiError
from ai_stp_api.slices.profile.avatar import (
    AVATAR_MAX_PIXELS,
    AVATAR_OUTPUT_SIZE,
    normalize_avatar,
    validate_provider_url,
)


@pytest.mark.parametrize(
    ("format", "mime"), [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_avatar_normalization_keeps_pixels_and_removes_metadata(format: str, mime: str) -> None:
    source = image_bytes(
        size=(AVATAR_OUTPUT_SIZE * 2, AVATAR_OUTPUT_SIZE), format=format, metadata=True
    )
    result = normalize_avatar(source, mime)
    with Image.open(BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == (AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE // 2)
        assert not image.getexif()
        assert "private_note" not in image.info
    assert b"must not be public" not in result


@pytest.mark.parametrize("payload", [b"", b"\x89PNG\r\n\x1a\n" + b"0" * 64, b"<html>error</html>"])
def test_avatar_rejects_undecodable_bytes(payload: bytes) -> None:
    with pytest.raises(ApiError):
        normalize_avatar(payload, "image/png")


def test_avatar_rejects_mime_mismatch() -> None:
    with pytest.raises(ApiError):
        normalize_avatar(image_bytes(), "image/jpeg")


def test_avatar_rejects_excess_pixels_before_decode() -> None:
    side = int(AVATAR_MAX_PIXELS**0.5) + 1
    with pytest.raises(ApiError):
        normalize_avatar(image_bytes(size=(side, side)), "image/png")


@pytest.mark.parametrize(
    "url",
    [
        "http://avatars.githubusercontent.com/u/1",
        "https://localhost/a",
        "https://127.0.0.1/a",
        "https://avatars.githubusercontent.com.evil.test/a",
        "https://user@avatars.githubusercontent.com/a",
        "https://avatars.githubusercontent.com:444/a",
        "https://lh3.googleusercontent.com/a",
    ],
)
def test_github_avatar_url_rejects_foreign_or_unsafe_hosts(url: str) -> None:
    with pytest.raises(ApiError):
        validate_provider_url(url, "github")
