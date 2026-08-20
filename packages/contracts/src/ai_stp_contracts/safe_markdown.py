"""Safe limited Markdown validation and render (SPEC-029).

Pure functions: no I/O. Renderer version is pinned as commonmark_v1.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Final

RENDERER_VERSION: Final = "commonmark_v1"
DESCRIPTION_MAX_BYTES: Final = 16 * 1024
EXCERPT_MAX_CHARS: Final = 280

_FORBIDDEN = re.compile(
    r"(?is)<\s*(script|style|iframe|object|embed|form|input|img|svg)\b|javascript:|data:|on\w+\s*="
)
_LINK = re.compile(r'\[([^\]]+)\]\((https://[^\s)]+|#[^\s)]*)(?:\s+["\']([^"\']+)["\'])?\)')
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.M)
_CODE_FENCE = re.compile(r"```[\w-]*\n(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_EMPH = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_MD_STRIP = re.compile(r"[#*_`\[\]()>|-]+")


class MarkdownValidationError(ValueError):
    """Invalid description Markdown."""


@dataclass(frozen=True, slots=True)
class RenderedMarkdown:
    html: str
    excerpt: str
    renderer_version: str
    source_digest: str


def source_digest(source: str) -> str:
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def validate_description(source: str) -> str:
    raw = source
    if len(raw.encode("utf-8")) > DESCRIPTION_MAX_BYTES:
        raise MarkdownValidationError("description exceeds 16 KiB")
    if _FORBIDDEN.search(raw):
        raise MarkdownValidationError("forbidden markup or scheme")
    for match in _LINK.finditer(raw):
        dest = match.group(2).strip()
        if dest.startswith("#"):
            continue
        if not dest.lower().startswith("https://"):
            raise MarkdownValidationError("link must be https or fragment")
        if "@" in dest.split("://", 1)[-1].split("/")[0]:
            raise MarkdownValidationError("credential-bearing url rejected")
    plain = excerpt_from_source(raw)
    if plain.strip() == "":
        raise MarkdownValidationError("description empty after markdown strip")
    return raw


def excerpt_from_source(source: str) -> str:
    text = _CODE_FENCE.sub(r"\1", source)
    text = _LINK.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MD_STRIP.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= EXCERPT_MAX_CHARS:
        return text
    return text[: EXCERPT_MAX_CHARS - 1].rstrip() + "…"


def render_description(source: str) -> RenderedMarkdown:
    """Validate and produce sanitized HTML + excerpt."""
    raw = validate_description(source)
    body = raw
    # Escape first, then re-introduce limited structures from source lines.
    # Simple block pipeline: fenced code, paragraphs, headings, lists-ish.
    parts: list[str] = []
    # Extract fenced blocks first with placeholders
    fences: list[str] = []

    def _store_fence(match: re.Match[str]) -> str:
        code = html.escape(match.group(1).rstrip("\n"))
        fences.append(f"<pre><code>{code}</code></pre>")
        return f"\n@@FENCE{len(fences) - 1}@@\n"

    body = _CODE_FENCE.sub(_store_fence, body)
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if not block:
            continue
        if re.fullmatch(r"@@FENCE(\d+)@@", block):
            idx = int(block[7:-2])
            parts.append(fences[idx])
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", block)
        if heading and "\n" not in block:
            level = min(len(heading.group(1)), 3) + 1  # h2-h4 in page
            inner = _inline(heading.group(2))
            parts.append(f"<h{level}>{inner}</h{level}>")
            continue
        lines = block.split("\n")
        if _is_table(lines):
            headers = _table_cells(lines[0])
            rows = [_table_cells(line) for line in lines[2:]]
            head = "".join(f"<th>{_inline(cell)}</th>" for cell in headers)
            body_rows = "".join(
                "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table>")
            continue
        if all(re.match(r"^[-*]\s+", line) for line in lines):
            items = "".join(f"<li>{_inline(re.sub(r'^[-*]\\s+', '', line))}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
            continue
        if all(re.match(r"^\d+\.\s+", line) for line in lines):
            items = "".join(
                f"<li>{_inline(re.sub(r'^\\d+\\.\\s+', '', line))}</li>" for line in lines
            )
            parts.append(f"<ol>{items}</ol>")
            continue
        parts.append(f"<p>{_inline(block.replace(chr(10), ' '))}</p>")

    return RenderedMarkdown(
        html="".join(parts),
        excerpt=excerpt_from_source(raw),
        renderer_version=RENDERER_VERSION,
        source_digest=source_digest(raw),
    )


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table(lines: list[str]) -> bool:
    if len(lines) < 2 or "|" not in lines[0]:
        return False
    separators = _table_cells(lines[1])
    return bool(separators) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separators)


def _inline(text: str) -> str:
    # Escape then apply limited inline patterns from original tokens carefully:
    # work on escaped text only for non-link parts by reconstructing from source.
    # Strategy: process links/code/bold/emph on unescaped, escaping leaf text.
    def esc(s: str) -> str:
        return html.escape(s, quote=True)

    out = text

    def link_sub(m: re.Match[str]) -> str:
        label = esc(m.group(1))
        dest = m.group(2).strip()
        href = esc(dest)
        title = f' title="{esc(m.group(3))}"' if m.group(3) else ""
        return f'<a href="{href}"{title} rel="noopener noreferrer">{label}</a>'

    out = _LINK.sub(link_sub, out)

    def code_sub(m: re.Match[str]) -> str:
        return f"<code>{esc(m.group(1))}</code>"

    out = _INLINE_CODE.sub(code_sub, out)

    def bold_sub(m: re.Match[str]) -> str:
        return f"<strong>{esc(m.group(1))}</strong>"

    out = _BOLD.sub(bold_sub, out)

    def emph_sub(m: re.Match[str]) -> str:
        return f"<em>{esc(m.group(1))}</em>"

    out = _EMPH.sub(emph_sub, out)

    # Escape remaining raw fragments that are not tags we introduced.
    # Split on our tags and escape plain segments.
    pieces = re.split(r"(</?(?:a|code|strong|em)\b[^>]*>)", out)
    rebuilt: list[str] = []
    for piece in pieces:
        if piece.startswith("<") and piece.endswith(">"):
            rebuilt.append(piece)
        else:
            rebuilt.append(esc(piece))
    return "".join(rebuilt)
