"""Canonical article digests (SPEC-054)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_stp_contracts.content import (
    ARTICLE_ACTIVE_DOMAIN,
    ARTICLE_REVISION_DOMAIN,
    ARTICLE_SNAPSHOT_DOMAIN,
    CONTENT_REPOSITORY,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.revisions import revision_id


def article_identity(article_type: str, slug: str) -> str:
    return f"{article_type}:{slug}"


def revision_content_digest(
    *,
    article_type: str,
    slug: str,
    locale: str,
    title: str,
    description: str,
    published_at: str,
    tags: Sequence[str],
    body: str,
    source_kind: str,
    source_ref: str | None,
    source_path: str | None,
) -> str:
    payload: dict[str, JsonValue] = {
        "type": article_type,
        "slug": slug,
        "locale": locale,
        "title": title,
        "description": description,
        "published_at": published_at,
        "tags": list(tags),
        "body": body,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "source_path": source_path,
    }
    return digest_canonical(ARTICLE_REVISION_DOMAIN, payload)


def article_revision_id(*, article_id: str, locale: str, content_digest: str) -> str:
    return revision_id(
        {"article_id": article_id, "locale": locale, "content_digest": content_digest}
    )


def active_digest(revision_ids: Mapping[str, str]) -> str:
    payload: dict[str, JsonValue] = {
        "en": revision_ids["en"],
        "ru": revision_ids["ru"],
    }
    return digest_canonical(ARTICLE_ACTIVE_DOMAIN, payload)


def snapshot_digest(*, repository: str, commit: str, entries: Sequence[Mapping[str, Any]]) -> str:
    ordered: list[JsonValue] = []
    for entry in sorted(
        entries,
        key=lambda item: (str(item["type"]), str(item["slug"]), str(item["locale"])),
    ):
        ordered.append(
            {
                "type": entry["type"],
                "slug": entry["slug"],
                "locale": entry["locale"],
                "title": entry["title"],
                "description": entry["description"],
                "published_at": entry["published_at"],
                "tags": list(entry["tags"]),
                "body": entry["body"],
                "content_digest": entry["content_digest"],
                "source_kind": entry["source_kind"],
                "source_ref": entry["source_ref"],
                "source_path": entry["source_path"],
            }
        )
    payload: dict[str, JsonValue] = {
        "repository": repository or CONTENT_REPOSITORY,
        "commit": commit,
        "entries": ordered,
    }
    return digest_canonical(ARTICLE_SNAPSHOT_DOMAIN, payload)


def public_list_etag(items: Sequence[Mapping[str, str]]) -> str:
    ordered: list[JsonValue] = [
        {"article_id": item["article_id"], "revision_id": item["revision_id"]}
        for item in sorted(items, key=lambda row: row["article_id"])
    ]
    return digest_canonical(ARTICLE_ACTIVE_DOMAIN, {"items": ordered})
