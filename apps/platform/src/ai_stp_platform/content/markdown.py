"""Safe Markdown policy for article bodies (SPEC-054 REQ-5413)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import cast
from urllib.parse import ParseResult, parse_qs, urlparse

from ai_stp_contracts.content import CONTENT_BODY_MAX
from ai_stp_platform.content.errors import ContentError

_FORBIDDEN_TAGS = frozenset(
    {"script", "style", "iframe", "object", "embed", "form", "input", "img", "svg"}
)
_ILLUSTRATION_PREFIX = "/content/illustrations/"
_HTTPS_PREFIX = "https://"
_VIDEO: re.Pattern[str] = re.compile(r"@\[(youtube|vimeo)\]\((https://[^)\s]+)\)", re.IGNORECASE)


def validate_article_body(source: str) -> str:
    """Reject raw HTML, dangerous URLs and empty bodies. Relative illustration paths stay."""
    if not source.strip():
        raise ContentError("AI_STP_CONTENT_INVALID", "article body is empty")
    if len(source) > CONTENT_BODY_MAX:
        raise ContentError("AI_STP_CONTENT_INVALID", "article body exceeds the contract limit")
    if _has_forbidden_markup(source):
        raise ContentError("AI_STP_CONTENT_INVALID", "forbidden markup or scheme")
    for dest in _markdown_link_destinations(source):
        if dest.startswith("#"):
            continue
        if dest.startswith(_ILLUSTRATION_PREFIX):
            continue
        if dest.lower().startswith(_HTTPS_PREFIX):
            host = dest.split("://", 1)[-1].split("/")[0]
            if "@" in host:
                raise ContentError("AI_STP_CONTENT_INVALID", "credential-bearing url rejected")
            continue
        raise ContentError("AI_STP_CONTENT_INVALID", "link must be https, fragment or illustration")
    for kind, dest in cast(list[tuple[str, str]], _VIDEO.findall(source)):
        parsed: ParseResult = urlparse(dest)
        host = (parsed.hostname or "").lower()
        if kind.lower() == "youtube":
            video_id = (
                parsed.path.strip("/")
                if host == "youtu.be"
                else parse_qs(parsed.query).get("v", [""])[0]
            )
            allowed = (
                host in {"youtube.com", "www.youtube.com", "youtu.be"}
                and re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id) is not None
            )
        else:
            video_id = parsed.path.rstrip("/").split("/")[-1]
            allowed = (
                host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}
                and re.fullmatch(r"\d{1,12}", video_id) is not None
            )
        if not allowed:
            raise ContentError(
                "AI_STP_CONTENT_INVALID", "video must be a supported YouTube or Vimeo URL"
            )
    return source


def _has_forbidden_markup(source: str) -> bool:
    lowered = source.lower()
    return (
        "javascript:" in lowered
        or "data:" in lowered
        or _has_forbidden_tag(lowered)
        or _has_event_handler_attr(lowered)
    )


def _is_word_char(char: str) -> bool:
    return char == "_" or char.isalnum()


def _has_forbidden_tag(lowered: str) -> bool:
    n = len(lowered)
    index = 0
    while index < n:
        start = lowered.find("<", index)
        if start < 0:
            return False
        cursor = start + 1
        while cursor < n and lowered[cursor].isspace():
            cursor += 1
        name_end = cursor
        while name_end < n and "a" <= lowered[name_end] <= "z":
            name_end += 1
        if (
            name_end > cursor
            and lowered[cursor:name_end] in _FORBIDDEN_TAGS
            and (name_end == n or not _is_word_char(lowered[name_end]))
        ):
            return True
        index = start + 1
    return False


def _has_event_handler_attr(lowered: str) -> bool:
    return re.search(r"(?<![a-z0-9_])on[a-z]+\s*=", lowered) is not None


def _markdown_link_destinations(source: str) -> Iterator[str]:
    """Yield destinations of complete `[…](…)` / `![…](…)` links. Always linear."""
    n = len(source)
    index = 0
    while index < n:
        if source[index] == "!" and index + 1 < n and source[index + 1] == "[":
            bracket = index + 1
        elif source[index] == "[":
            bracket = index
        else:
            index += 1
            continue
        label_end = bracket + 1
        while label_end < n and source[label_end] != "]":
            label_end += 1
        if label_end >= n:
            return
        dest_index = label_end + 1
        if dest_index >= n or source[dest_index] != "(":
            index = bracket + 1
            continue
        dest_index += 1
        taken = _take_link_destination(source, dest_index)
        if taken is None:
            index = bracket + 1
            continue
        dest, after_dest, exhausted = taken
        if exhausted:
            return
        closer = after_dest
        if closer < n and source[closer] == ")":
            yield dest
            index = closer + 1
            continue
        titled = _skip_markdown_title(source, closer)
        if titled is not None and titled < n and source[titled] == ")":
            yield dest
            index = titled + 1
            continue
        index = bracket + 1


def _take_link_destination(source: str, index: int) -> tuple[str, int, bool] | None:
    """Parse `https://…`, `/…`, or `#…`. `exhausted` means the rest of `source` has no `)`."""
    n = len(source)
    if source.startswith(_HTTPS_PREFIX, index):
        body = index + len(_HTTPS_PREFIX)
        end = _scan_dest_body(source, body)
        if end == body:
            return None
        return source[index:end], end, end == n
    if index < n and source[index] == "/":
        body = index + 1
        end = _scan_dest_body(source, body)
        if end == body:
            return None
        return source[index:end], end, end == n
    if index < n and source[index] == "#":
        end = _scan_dest_body(source, index + 1)
        return source[index:end], end, end == n
    return None


def _scan_dest_body(source: str, index: int) -> int:
    end = index
    n = len(source)
    while end < n and source[end] != ")" and not source[end].isspace():
        end += 1
    return end


def _skip_markdown_title(source: str, index: int) -> int | None:
    n = len(source)
    if index >= n or not source[index].isspace():
        return None
    cursor = index
    while cursor < n and source[cursor].isspace():
        cursor += 1
    if cursor >= n or source[cursor] not in "\"'":
        return None
    cursor += 1
    title_start = cursor
    while cursor < n and source[cursor] not in "\"'":
        cursor += 1
    if cursor == title_start or cursor >= n:
        return None
    return cursor + 1
