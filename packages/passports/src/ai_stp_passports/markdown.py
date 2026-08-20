"""Closed safe-Markdown profile for immutable version descriptions (SPEC-029)."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Final, Literal
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from pydantic import BaseModel, ConfigDict

DESCRIPTION_FORMAT: Final[Literal["commonmark_v1"]] = "commonmark_v1"
RENDERER_VERSION: Final[Literal["safe_markdown_v1"]] = "safe_markdown_v1"
MAX_DESCRIPTION_BYTES: Final[int] = 16 * 1024
MAX_DESCRIPTION_LINES: Final[int] = 256
MAX_EXCERPT_CODEPOINTS: Final[int] = 240
MAX_TOKEN_NESTING: Final[int] = 32

type MarkdownPolicyCode = Literal[
    "empty",
    "too_large",
    "too_many_lines",
    "not_nfc",
    "non_lf_newline",
    "control_character",
    "raw_html",
    "image",
    "unsafe_link",
    "unsupported_token",
    "empty_text",
    "unsupported_renderer",
]

_ALLOWED_BLOCK_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "paragraph_open",
        "paragraph_close",
        "inline",
        "heading_open",
        "heading_close",
        "blockquote_open",
        "blockquote_close",
        "bullet_list_open",
        "bullet_list_close",
        "ordered_list_open",
        "ordered_list_close",
        "list_item_open",
        "list_item_close",
        "fence",
        "code_block",
        "hr",
    }
)
_ALLOWED_INLINE_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "text",
        "softbreak",
        "hardbreak",
        "code_inline",
        "em_open",
        "em_close",
        "strong_open",
        "strong_close",
        "link_open",
        "link_close",
    }
)
_TEXT_TOKENS: Final[frozenset[str]] = frozenset({"text", "code_inline"})
_BLOCK_TEXT_TOKENS: Final[frozenset[str]] = frozenset({"fence", "code_block"})
_BLOCK_BOUNDARIES: Final[frozenset[str]] = frozenset(
    {
        "paragraph_close",
        "heading_close",
        "blockquote_close",
        "list_item_close",
        "bullet_list_close",
        "ordered_list_close",
        "hr",
        "fence",
        "code_block",
    }
)


class MarkdownPolicyError(ValueError):
    """Stable policy failure without reflecting the untrusted source."""

    def __init__(self, code: MarkdownPolicyCode) -> None:
        self.code = code
        super().__init__(f"safe Markdown policy rejected the description: {code}")


class SafeMarkdownProjection(BaseModel):
    """Deterministic projections of one already-validated description."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    description_format: Literal["commonmark_v1"] = DESCRIPTION_FORMAT
    renderer_version: Literal["safe_markdown_v1"] = RENDERER_VERSION
    html: str
    excerpt: str


def _parser() -> MarkdownIt:
    parser = MarkdownIt(
        "commonmark",
        {
            "html": True,
            "linkify": False,
            "typographer": False,
            "breaks": False,
            "maxNesting": MAX_TOKEN_NESTING,
        },
    )
    # The parser normally turns dangerous links back into text. Accept every
    # syntactically valid destination here so the policy can reject it rather
    # than silently changing its meaning.
    parser.validateLink = _accept_link
    return parser


def _accept_link(url: str) -> bool:
    del url
    return True


def _validate_link(destination: str) -> None:
    if destination.startswith("#"):
        if len(destination) == 1 or any(char.isspace() for char in destination):
            raise MarkdownPolicyError("unsafe_link")
        return
    if "\\" in destination:
        raise MarkdownPolicyError("unsafe_link")
    try:
        parsed = urlsplit(destination)
        port = parsed.port
    except ValueError as error:
        raise MarkdownPolicyError("unsafe_link") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise MarkdownPolicyError("unsafe_link")


def _validate_tokens(tokens: list[Token]) -> None:
    for token in tokens:
        if token.level > MAX_TOKEN_NESTING:
            raise MarkdownPolicyError("unsupported_token")
        if token.type in {"html_block", "html_inline"}:
            raise MarkdownPolicyError("raw_html")
        if token.type == "image":
            raise MarkdownPolicyError("image")
        allowed = _ALLOWED_INLINE_TOKENS if token.type not in _ALLOWED_BLOCK_TOKENS else None
        if allowed is not None and token.type not in allowed:
            raise MarkdownPolicyError("unsupported_token")
        if token.type == "link_open":
            destination = token.attrGet("href")
            if not isinstance(destination, str):
                raise MarkdownPolicyError("unsafe_link")
            _validate_link(destination)
        if token.children:
            _validate_tokens(token.children)


def _parse(source: str) -> tuple[MarkdownIt, list[Token]]:
    if not source or not source.strip():
        raise MarkdownPolicyError("empty")
    if "\r" in source:
        raise MarkdownPolicyError("non_lf_newline")
    if any(
        char not in {"\n", "\t"} and unicodedata.category(char) in {"Cc", "Cf", "Cs"}
        for char in source
    ):
        raise MarkdownPolicyError("control_character")
    if unicodedata.normalize("NFC", source) != source:
        raise MarkdownPolicyError("not_nfc")
    if len(source.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise MarkdownPolicyError("too_large")
    if source.count("\n") + 1 > MAX_DESCRIPTION_LINES:
        raise MarkdownPolicyError("too_many_lines")

    parser = _parser()
    tokens = parser.parse(source)
    _validate_tokens(tokens)
    return parser, tokens


def _plain_text(tokens: Iterable[Token]) -> str:
    fragments: list[str] = []
    for token in tokens:
        if token.type in _TEXT_TOKENS or token.type in _BLOCK_TEXT_TOKENS:
            fragments.append(token.content)
        elif token.type in {"softbreak", "hardbreak"} or token.type in _BLOCK_BOUNDARIES:
            fragments.append(" ")
        if token.children:
            fragments.append(_plain_text(token.children))
    return " ".join("".join(fragments).split())


def _excerpt(tokens: list[Token]) -> str:
    text = _plain_text(tokens)
    if not text:
        raise MarkdownPolicyError("empty_text")
    if len(text) <= MAX_EXCERPT_CODEPOINTS:
        return text
    prefix = text[: MAX_EXCERPT_CODEPOINTS - 1].rstrip()
    if not text[MAX_EXCERPT_CODEPOINTS - 1].isspace():
        boundary = prefix.rfind(" ")
        if boundary >= MAX_EXCERPT_CODEPOINTS // 2:
            prefix = prefix[:boundary].rstrip()
    return f"{prefix}…"


def _render_link_open(
    renderer: RendererHTML,
    tokens: list[Token],
    index: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    token = tokens[index]
    raw_destination = token.attrGet("href")
    destination = raw_destination if isinstance(raw_destination, str) else ""
    if not destination.startswith("#"):
        token.attrSet("rel", "nofollow noopener noreferrer")
    return renderer.renderToken(tokens, index, options, env)


def project_safe_markdown(
    source: str,
    *,
    renderer_version: str = RENDERER_VERSION,
) -> SafeMarkdownProjection:
    """Validate and render an exact description under one versioned profile."""

    if renderer_version != RENDERER_VERSION:
        raise MarkdownPolicyError("unsupported_renderer")
    parser, tokens = _parse(source)
    parser.add_render_rule("link_open", _render_link_open)
    html = parser.renderer.render(tokens, parser.options, {})
    return SafeMarkdownProjection(html=html, excerpt=_excerpt(tokens))


def validate_safe_markdown(source: str) -> str:
    """Pydantic-friendly validator preserving the exact accepted source."""

    project_safe_markdown(source)
    return source
