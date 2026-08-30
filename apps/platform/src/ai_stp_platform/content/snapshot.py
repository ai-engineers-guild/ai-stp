"""Deterministic repository article snapshot (SPEC-054 REQ-5403)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ai_stp_contracts.content import (
    CONTENT_BODY_MAX,
    CONTENT_COMMIT_PATTERN,
    CONTENT_DATE_PATTERN,
    CONTENT_LOCALES,
    CONTENT_REPOSITORY,
    CONTENT_SLUG_PATTERN,
    CONTENT_SNAPSHOT_MAX_ENTRIES,
    CONTENT_TYPES,
    ContentRepositoryImportRequest,
    ContentSnapshotEntry,
)
from ai_stp_platform.content.digests import (
    revision_content_digest,
)
from ai_stp_platform.content.digests import (
    snapshot_digest as digest_snapshot,
)
from ai_stp_platform.content.errors import ContentError
from ai_stp_platform.content.markdown import validate_article_body

_FRONTMATTER = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")
_KEY = re.compile(r"^([a-z_]+):\s*(.*)$")
_LIST_ITEM = re.compile(r"^  - (.+)$")
_ALLOWED_META = frozenset(
    {"type", "slug", "locale", "title", "description", "published_at", "tags", "draft"}
)


def _today(now: datetime | None) -> date:
    moment = now or datetime.now(UTC)
    return moment.date()


def parse_published_date(value: str, *, today: date) -> str:
    if re.fullmatch(CONTENT_DATE_PATTERN, value) is None:
        raise ContentError("AI_STP_CONTENT_INVALID", "published_at is not a calendar date")
    year, month, day = (int(part) for part in value.split("-"))
    try:
        parsed = date(year, month, day)
    except ValueError as error:
        raise ContentError("AI_STP_CONTENT_INVALID", "published_at is not a real date") from error
    if parsed > today:
        raise ContentError("AI_STP_CONTENT_INVALID", "published_at must not be in the future")
    return value


def _parse_tags(raw: str) -> list[str]:
    text = raw.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ContentError("AI_STP_CONTENT_INVALID", "tags must be a YAML list")
    inner = text[1:-1].strip()
    if not inner:
        return []
    tags = [item.strip().strip("'\"") for item in inner.split(",")]
    if any(not tag for tag in tags):
        raise ContentError("AI_STP_CONTENT_INVALID", "empty tag")
    if len(tags) != len(set(tags)):
        raise ContentError("AI_STP_CONTENT_INVALID", "duplicate tags are rejected")
    if len(tags) > 12:
        raise ContentError("AI_STP_CONTENT_INVALID", "too many tags")
    return tags


def _parse_bool(raw: str) -> bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ContentError("AI_STP_CONTENT_INVALID", "draft must be true or false")


def parse_frontmatter(source: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER.match(source)
    if match is None:
        raise ContentError("AI_STP_CONTENT_INVALID", "content entry lacks YAML frontmatter")
    meta: dict[str, Any] = {}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        keyed = _KEY.match(line)
        if keyed is None:
            raise ContentError("AI_STP_CONTENT_INVALID", "invalid frontmatter line")
        key, value = keyed.group(1), keyed.group(2).strip()
        if key not in _ALLOWED_META:
            raise ContentError("AI_STP_CONTENT_INVALID", f"unknown frontmatter field: {key}")
        if key in meta:
            raise ContentError("AI_STP_CONTENT_INVALID", f"duplicate frontmatter field: {key}")
        if key == "tags" and not value:
            tags: list[str] = []
            index += 1
            while index < len(lines):
                item = _LIST_ITEM.match(lines[index])
                if item is None:
                    break
                tags.append(item.group(1).strip().strip("'\""))
                index += 1
            meta[key] = "[" + ", ".join(tags) + "]"
            continue
        meta[key] = value
        index += 1
    body = (match.group(2) or "").strip()
    if not body:
        raise ContentError("AI_STP_CONTENT_INVALID", "content entry body is empty")
    if len(body) > CONTENT_BODY_MAX:
        raise ContentError("AI_STP_CONTENT_INVALID", "article body exceeds the contract limit")
    return meta, body


def _entry_from_file(
    path: Path,
    *,
    hub: Path,
    commit: str,
    today: date,
) -> ContentSnapshotEntry | None:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    if _parse_bool(str(meta.get("draft", "false"))):
        return None
    article_type = str(meta.get("type", ""))
    slug = str(meta.get("slug", ""))
    locale = str(meta.get("locale", ""))
    title = str(meta.get("title", ""))
    description = str(meta.get("description", ""))
    published_at = parse_published_date(str(meta.get("published_at", "")), today=today)
    tags = sorted(_parse_tags(str(meta.get("tags", "[]"))))
    if article_type not in CONTENT_TYPES:
        raise ContentError("AI_STP_CONTENT_INVALID", "unknown article type")
    if re.fullmatch(CONTENT_SLUG_PATTERN, slug) is None or len(slug) > 120:
        raise ContentError("AI_STP_CONTENT_INVALID", "invalid slug")
    if locale not in CONTENT_LOCALES:
        raise ContentError("AI_STP_CONTENT_INVALID", "locale must be ru or en")
    if not (1 <= len(title) <= 160):
        raise ContentError("AI_STP_CONTENT_INVALID", "invalid title")
    if not (1 <= len(description) <= 320):
        raise ContentError("AI_STP_CONTENT_INVALID", "invalid description")
    validate_article_body(body)
    relative = path.relative_to(hub).as_posix()
    digest = revision_content_digest(
        article_type=article_type,
        slug=slug,
        locale=locale,
        title=title,
        description=description,
        published_at=published_at,
        tags=tags,
        body=body,
        source_kind="repository",
        source_ref=commit,
        source_path=relative,
    )
    return ContentSnapshotEntry(
        type=article_type,  # type: ignore[arg-type]
        slug=slug,
        locale=locale,  # type: ignore[arg-type]
        title=title,
        description=description,
        published_at=published_at,
        tags=tags,
        body=body,
        content_digest=digest,
        source_kind="repository",
        source_ref=commit,
        source_path=relative,
    )


def assert_locale_parity(entries: Iterable[ContentSnapshotEntry]) -> None:
    by_identity: dict[str, set[str]] = {}
    for entry in entries:
        identity = f"{entry.type}:{entry.slug}"
        by_identity.setdefault(identity, set()).add(entry.locale)
    missing: list[str] = []
    for identity, locales in sorted(by_identity.items()):
        if locales != set(CONTENT_LOCALES):
            missing.append(identity)
    if missing:
        raise ContentError(
            "AI_STP_CONTENT_INVALID",
            "content locale parity failed: " + ", ".join(missing),
        )


def build_repository_snapshot(
    hub: Path,
    *,
    commit: str,
    now: datetime | None = None,
    expected_generation: int = 0,
) -> ContentRepositoryImportRequest:
    """Build a full published snapshot from apps/web/content/hub. No network."""
    if re.fullmatch(CONTENT_COMMIT_PATTERN, commit) is None:
        raise ContentError("AI_STP_CONTENT_INVALID", "commit must be an exact 40-hex SHA")
    if commit == "0" * 40:
        raise ContentError(
            "AI_STP_CONTENT_INVALID",
            "commit placeholder is not a real SHA",
        )
    if not hub.is_dir():
        raise ContentError("AI_STP_CONTENT_INVALID", "content hub directory is missing")
    today = _today(now)
    markdown_files = [path for path in sorted(hub.rglob("*.md")) if path.is_file()]
    if not markdown_files:
        raise ContentError(
            "AI_STP_CONTENT_INVALID",
            "content hub contains no markdown files",
        )
    entries: list[ContentSnapshotEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for path in markdown_files:
        entry = _entry_from_file(path, hub=hub, commit=commit, today=today)
        if entry is None:
            continue
        key = (entry.type, entry.slug, entry.locale)
        if key in seen:
            raise ContentError(
                "AI_STP_CONTENT_INVALID",
                f"duplicate content entry: {entry.locale}:{entry.type}:{entry.slug}",
            )
        seen.add(key)
        entries.append(entry)
    if len(entries) > CONTENT_SNAPSHOT_MAX_ENTRIES:
        raise ContentError("AI_STP_CONTENT_INVALID", "snapshot exceeds entry limit")
    assert_locale_parity(entries)
    ordered = sorted(entries, key=lambda item: (item.type, item.slug, item.locale))
    digest = digest_snapshot(
        repository=CONTENT_REPOSITORY,
        commit=commit,
        entries=[item.model_dump(mode="json") for item in ordered],
    )
    return ContentRepositoryImportRequest(
        schema_version=1,
        repository=CONTENT_REPOSITORY,
        commit=commit,
        snapshot_digest=digest,
        expected_generation=expected_generation,
        entries=ordered,
    )


def verify_snapshot_digests(
    snapshot: ContentRepositoryImportRequest,
    *,
    now: datetime | None = None,
) -> None:
    """Recompute every digest. File order is irrelevant."""
    seen: set[tuple[str, str, str]] = set()
    today = _today(now)
    for entry in snapshot.entries:
        key = (entry.type, entry.slug, entry.locale)
        if key in seen:
            raise ContentError("AI_STP_CONTENT_INVALID", "duplicate snapshot entry")
        seen.add(key)
        expected = revision_content_digest(
            article_type=entry.type,
            slug=entry.slug,
            locale=entry.locale,
            title=entry.title,
            description=entry.description,
            published_at=entry.published_at,
            tags=sorted(entry.tags),
            body=entry.body,
            source_kind=entry.source_kind,
            source_ref=entry.source_ref,
            source_path=entry.source_path,
        )
        if expected != entry.content_digest:
            raise ContentError("AI_STP_CONTENT_INVALID", "article content digest mismatch")
        if entry.source_ref != snapshot.commit:
            raise ContentError("AI_STP_CONTENT_INVALID", "entry commit must match snapshot commit")
        if entry.source_kind != "repository":
            raise ContentError(
                "AI_STP_CONTENT_INVALID", "snapshot entries must be repository-owned"
            )
        parse_published_date(entry.published_at, today=today)
        validate_article_body(entry.body)
    assert_locale_parity(snapshot.entries)
    recomputed = digest_snapshot(
        repository=snapshot.repository,
        commit=snapshot.commit,
        entries=[item.model_dump(mode="json") for item in snapshot.entries],
    )
    if recomputed != snapshot.snapshot_digest:
        raise ContentError("AI_STP_CONTENT_INVALID", "snapshot digest mismatch")


def snapshot_as_json(snapshot: ContentRepositoryImportRequest) -> Mapping[str, Any]:
    return snapshot.model_dump(mode="json")
