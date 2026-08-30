"""Safe Markdown policy for article bodies (SPEC-054 REQ-5413)."""

from __future__ import annotations

import re

from ai_stp_contracts.content import CONTENT_BODY_MAX
from ai_stp_platform.content.errors import ContentError

_FORBIDDEN = re.compile(
    r"(?is)<\s*(script|style|iframe|object|embed|form|input|img|svg)\b|javascript:|data:|on\w+\s*="
)
_LINK = re.compile(r"!?\[[^\]]*\]\((https://[^\s)]+|/[^\s)]+|#[^\s)]*)(?:\s+[\"'][^\"']+[\"'])?\)")


def validate_article_body(source: str) -> str:
    """Reject raw HTML, dangerous URLs and empty bodies. Relative illustration paths stay."""
    if not source.strip():
        raise ContentError("AI_STP_CONTENT_INVALID", "article body is empty")
    if len(source) > CONTENT_BODY_MAX:
        raise ContentError("AI_STP_CONTENT_INVALID", "article body exceeds the contract limit")
    if _FORBIDDEN.search(source):
        raise ContentError("AI_STP_CONTENT_INVALID", "forbidden markup or scheme")
    for match in _LINK.finditer(source):
        dest = match.group(1).strip()
        if dest.startswith("#"):
            continue
        if dest.startswith("/content/illustrations/"):
            continue
        if dest.lower().startswith("https://"):
            host = dest.split("://", 1)[-1].split("/")[0]
            if "@" in host:
                raise ContentError("AI_STP_CONTENT_INVALID", "credential-bearing url rejected")
            continue
        raise ContentError("AI_STP_CONTENT_INVALID", "link must be https, fragment or illustration")
    return source
