"""Bounded provider fetch and metadata-free avatar normalization (SPEC-028)."""

from __future__ import annotations

import warnings
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, ImageOps

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_contracts.public_profile import AVATAR_MAX_BYTES, validate_avatar_upload

AVATAR_MAX_PIXELS = 16_777_216
AVATAR_OUTPUT_SIZE = 512
AVATAR_REDIRECT_LIMIT = 3
_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def validate_provider_url(url: str, provider: str) -> None:
    """Only HTTPS provider-owned image hosts may receive an unauthenticated fetch."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        allowed = (
            host
            in {
                "avatars.githubusercontent.com",
                "avatars0.githubusercontent.com",
                "avatars1.githubusercontent.com",
                "avatars2.githubusercontent.com",
                "avatars3.githubusercontent.com",
            }
            if provider == "github"
            else host == "lh3.googleusercontent.com" or host.endswith(".googleusercontent.com")
        )
        if (
            provider not in {"github", "google"}
            or not allowed
            or parsed.scheme != "https"
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("invalid provider image URL")
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "avatar source host not allowed") from exc


async def fetch_provider_avatar(
    client: httpx.AsyncClient, url: str, provider: str
) -> tuple[bytes, str]:
    """Validate every hop and stop reading as soon as the decoded byte limit is exceeded."""
    current = url
    for hop in range(AVATAR_REDIRECT_LIMIT + 1):
        validate_provider_url(current, provider)
        try:
            async with client.stream(
                "GET", current, follow_redirects=False, timeout=10.0
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = response.headers.get("location")
                    if not target or hop == AVATAR_REDIRECT_LIMIT:
                        raise ApiError(
                            ErrorCategory.DEPENDENCY, "avatar source redirect limit exceeded"
                        )
                    current = urljoin(current, target)
                    continue
                if response.status_code != 200:
                    raise ApiError(ErrorCategory.DEPENDENCY, "avatar source fetch failed")
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                try:
                    validate_avatar_upload(content_type=content_type, size_bytes=1)
                except ValueError as exc:
                    raise ApiError(
                        ErrorCategory.VALIDATION, "avatar source is not a supported image"
                    ) from exc
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > AVATAR_MAX_BYTES:
                        raise ApiError(ErrorCategory.VALIDATION, "avatar exceeds 5 MiB limit")
                    chunks.extend(chunk)
                return bytes(chunks), content_type
        except httpx.HTTPError as exc:
            raise ApiError(ErrorCategory.DEPENDENCY, "avatar source fetch failed") from exc
    raise ApiError(ErrorCategory.DEPENDENCY, "avatar source fetch failed")


def normalize_avatar(payload: bytes, content_type: str) -> bytes:
    """Decode only accepted formats, bound pixels, orient, resize and emit fresh PNG pixels."""
    try:
        validate_avatar_upload(content_type=content_type, size_bytes=len(payload))
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source = Image.open(BytesIO(payload), formats=list(_FORMATS.values()))
        with source:
            if source.format != _FORMATS[content_type]:
                raise ValueError("avatar content does not match its media type")
            if source.width * source.height > AVATAR_MAX_PIXELS:
                raise ValueError("avatar exceeds pixel limit")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            oriented.thumbnail((AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE), Image.Resampling.LANCZOS)
            # New pixels prevent EXIF, XMP, ICC and text chunks from following the input.
            converted = oriented.convert("RGBA")
            clean = Image.new("RGBA", converted.size)
            clean.paste(converted)
            output = BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ApiError(
            ErrorCategory.VALIDATION, "avatar image is invalid or exceeds its limits"
        ) from exc
