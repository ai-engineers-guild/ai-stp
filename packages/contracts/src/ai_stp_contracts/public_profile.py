"""Public profile wire shapes and pure validation (SPEC-028, docs/contracts/public-profile.md)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISPLAY_NAME_MAX: Final = 80
BIO_MAX: Final = 1500
LINK_LABEL_MAX: Final = 60
LINKS_MAX: Final = 8
AVATAR_MAX_BYTES: Final = 5 * 1024 * 1024
AVATAR_ALLOWED_MIME: Final = frozenset({"image/jpeg", "image/png", "image/webp"})

_HTTPS = re.compile(r"^https://", re.IGNORECASE)


class ProfileLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: Annotated[str, Field(min_length=1, max_length=LINK_LABEL_MAX)]
    url: Annotated[str, Field(min_length=8, max_length=2048)]

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        raw = value.strip()
        if not _HTTPS.match(raw):
            raise ValueError("link url must be https")
        parsed = urlparse(raw)
        if parsed.username or parsed.password:
            raise ValueError("link url must not include credentials")
        if not parsed.netloc:
            raise ValueError("link url must include host")
        # Normalize: drop fragment for identity; keep path/query.
        normalized = f"https://{parsed.netloc.lower()}{parsed.path or ''}"
        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"
        return normalized.rstrip("/") if parsed.path == "" else normalized


class ProfileFields(BaseModel):
    """Author-editable fields of a profile revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: Annotated[str | None, Field(default=None, max_length=DISPLAY_NAME_MAX)] = None
    bio: Annotated[str | None, Field(default=None, max_length=BIO_MAX)] = None
    links: list[ProfileLink] = Field(default_factory=lambda: list[ProfileLink]())
    avatar_asset_id: str | None = None

    @field_validator("display_name")
    @classmethod
    def name_bounds(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if text == "":
            return None
        if len(text) > DISPLAY_NAME_MAX:
            raise ValueError("display_name too long")
        return text

    @field_validator("bio")
    @classmethod
    def bio_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Allow limited Markdown (bold/code/links); reject raw HTML tags and script-like URIs.
        if re.search(r"<[^>\s]+[^>]*>", value) or re.search(
            r"javascript:|data:",
            value,
            flags=re.IGNORECASE,
        ):
            raise ValueError("bio must not contain HTML or unsafe URIs")
        if len(value) > BIO_MAX:
            raise ValueError("bio too long")
        return value

    @field_validator("links")
    @classmethod
    def unique_urls(cls, value: list[ProfileLink]) -> list[ProfileLink]:
        if len(value) > LINKS_MAX:
            raise ValueError("too many links")
        seen: set[str] = set()
        for link in value:
            if link.url in seen:
                raise ValueError("duplicate link url")
            seen.add(link.url)
        return value


def content_digest(fields: ProfileFields) -> str:
    """Deterministic digest of revision content."""
    payload = {
        "display_name": fields.display_name,
        "bio": fields.bio,
        "links": [{"label": link.label, "url": link.url} for link in fields.links],
        "avatar_asset_id": fields.avatar_asset_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def public_projection(
    *,
    account_id: str,
    fields: ProfileFields,
    avatar_public_url: str | None,
    author_verified: bool = False,
) -> dict[str, Any]:
    """Allowlist projection for public and owner-preview (same shape)."""
    return {
        "schema_version": 1,
        "kind": "public_profile",
        "account_id": account_id,
        "display_name": fields.display_name,
        "bio": fields.bio,
        "links": [{"label": link.label, "url": link.url} for link in fields.links],
        "avatar_url": avatar_public_url,
        "author_verified": author_verified,
    }


def is_empty_profile(fields: ProfileFields) -> bool:
    return (
        fields.display_name is None
        and (fields.bio is None or fields.bio == "")
        and len(fields.links) == 0
        and fields.avatar_asset_id is None
    )


def validate_avatar_upload(*, content_type: str, size_bytes: int) -> None:
    if content_type not in AVATAR_ALLOWED_MIME:
        raise ValueError("unsupported avatar mime type")
    if size_bytes <= 0 or size_bytes > AVATAR_MAX_BYTES:
        raise ValueError("avatar size out of bounds")


ProfileState = Literal["absent", "draft", "published", "asset_processing"]
