/**
 * Strict SPEC-029 profile for passport descriptions (untrusted publisher input).
 * Mirrors packages/passports/src/ai_stp_passports/markdown.py token-for-token;
 * the shared corpus safe-markdown-v1.json is the parity oracle.
 */

import MarkdownIt from "markdown-it";
import type Token from "markdown-it/lib/token.mjs";

const DESCRIPTION_FORMAT = "commonmark_v1";
const RENDERER_VERSION = "safe_markdown_v1";
const MAX_DESCRIPTION_BYTES = 16 * 1024;
const MAX_DESCRIPTION_LINES = 256;
const MAX_EXCERPT_CODEPOINTS = 240;
const MAX_TOKEN_NESTING = 32;

export type MarkdownPolicyCode =
  | "empty"
  | "too_large"
  | "too_many_lines"
  | "not_nfc"
  | "non_lf_newline"
  | "control_character"
  | "raw_html"
  | "image"
  | "unsafe_link"
  | "unsupported_token"
  | "empty_text"
  | "unsupported_renderer";

export class MarkdownPolicyError extends Error {
  readonly code: MarkdownPolicyCode;

  constructor(code: MarkdownPolicyCode) {
    super(`safe Markdown policy rejected the description: ${code}`);
    this.name = "MarkdownPolicyError";
    this.code = code;
  }
}

export type SafeMarkdownProjection = {
  description_format: typeof DESCRIPTION_FORMAT;
  renderer_version: typeof RENDERER_VERSION;
  html: string;
  excerpt: string;
};

const ALLOWED_BLOCK_TOKENS = new Set([
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
]);

const ALLOWED_INLINE_TOKENS = new Set([
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
]);

const TEXT_TOKENS = new Set(["text", "code_inline"]);
const BLOCK_TEXT_TOKENS = new Set(["fence", "code_block"]);
const BLOCK_BOUNDARIES = new Set([
  "paragraph_close",
  "heading_close",
  "blockquote_close",
  "list_item_close",
  "bullet_list_close",
  "ordered_list_close",
  "hr",
  "fence",
  "code_block",
]);

function parser(): MarkdownIt {
  // maxNesting exists at runtime but is absent from @types/markdown-it;
  // a named variable avoids the object-literal excess-property check.
  const options = {
    html: true,
    linkify: false,
    typographer: false,
    breaks: false,
    maxNesting: MAX_TOKEN_NESTING,
  };
  const md = new MarkdownIt("commonmark", options);
  // Accept every syntactically valid destination at parse time so the policy
  // rejects it instead of the parser silently changing its meaning.
  md.validateLink = () => true;
  return md;
}

function validateLink(destination: string): void {
  if (destination.startsWith("#")) {
    if (destination.length === 1 || /\s/u.test(destination)) {
      throw new MarkdownPolicyError("unsafe_link");
    }
    return;
  }
  if (destination.includes("\\")) {
    throw new MarkdownPolicyError("unsafe_link");
  }
  const match = /^https:\/\/([^/?#]*)/i.exec(destination);
  if (match === null) {
    throw new MarkdownPolicyError("unsafe_link");
  }
  const authority = match[1] ?? "";
  if (authority === "" || authority.includes("@")) {
    throw new MarkdownPolicyError("unsafe_link");
  }
  let host: string;
  let port = "";
  if (authority.startsWith("[")) {
    const close = authority.indexOf("]");
    if (close === -1) {
      throw new MarkdownPolicyError("unsafe_link");
    }
    host = authority.slice(0, close + 1);
    const rest = authority.slice(close + 1);
    if (rest !== "") {
      if (!rest.startsWith(":")) {
        throw new MarkdownPolicyError("unsafe_link");
      }
      port = rest.slice(1);
    }
  } else {
    const colon = authority.indexOf(":");
    if (colon === -1) {
      host = authority;
    } else {
      host = authority.slice(0, colon);
      port = authority.slice(colon + 1);
    }
    if (host.includes(":")) {
      throw new MarkdownPolicyError("unsafe_link");
    }
  }
  if (host === "") {
    throw new MarkdownPolicyError("unsafe_link");
  }
  if (port !== "") {
    if (!/^\d+$/.test(port)) {
      throw new MarkdownPolicyError("unsafe_link");
    }
    const parsed = Number.parseInt(port, 10);
    if (parsed < 1 || parsed > 65535) {
      throw new MarkdownPolicyError("unsafe_link");
    }
  }
}

function validateTokens(tokens: Token[]): void {
  for (const token of tokens) {
    if (token.level > MAX_TOKEN_NESTING) {
      throw new MarkdownPolicyError("unsupported_token");
    }
    if (token.type === "html_block" || token.type === "html_inline") {
      throw new MarkdownPolicyError("raw_html");
    }
    if (token.type === "image") {
      throw new MarkdownPolicyError("image");
    }
    if (!ALLOWED_BLOCK_TOKENS.has(token.type) && !ALLOWED_INLINE_TOKENS.has(token.type)) {
      throw new MarkdownPolicyError("unsupported_token");
    }
    if (token.type === "link_open") {
      const destination = token.attrGet("href");
      if (typeof destination !== "string") {
        throw new MarkdownPolicyError("unsafe_link");
      }
      validateLink(destination);
    }
    if (token.children !== null && token.children.length > 0) {
      validateTokens(token.children);
    }
  }
}

function parse(source: string): { md: MarkdownIt; tokens: Token[] } {
  if (source === "" || source.trim() === "") {
    throw new MarkdownPolicyError("empty");
  }
  if (source.includes("\r")) {
    throw new MarkdownPolicyError("non_lf_newline");
  }
  for (const char of source) {
    if (char !== "\n" && char !== "\t" && /[\p{Cc}\p{Cf}\p{Cs}]/u.test(char)) {
      throw new MarkdownPolicyError("control_character");
    }
  }
  if (source.normalize("NFC") !== source) {
    throw new MarkdownPolicyError("not_nfc");
  }
  if (new TextEncoder().encode(source).length > MAX_DESCRIPTION_BYTES) {
    throw new MarkdownPolicyError("too_large");
  }
  if (source.split("\n").length > MAX_DESCRIPTION_LINES) {
    throw new MarkdownPolicyError("too_many_lines");
  }
  const md = parser();
  const tokens = md.parse(source, {});
  validateTokens(tokens);
  return { md, tokens };
}

function plainText(tokens: Token[]): string {
  const fragments: string[] = [];
  for (const token of tokens) {
    if (TEXT_TOKENS.has(token.type) || BLOCK_TEXT_TOKENS.has(token.type)) {
      fragments.push(token.content);
    } else if (
      token.type === "softbreak" ||
      token.type === "hardbreak" ||
      BLOCK_BOUNDARIES.has(token.type)
    ) {
      fragments.push(" ");
    }
    if (token.children !== null && token.children.length > 0) {
      fragments.push(plainText(token.children));
    }
  }
  return fragments
    .join("")
    .split(/\s+/)
    .filter((part) => part !== "")
    .join(" ");
}

function excerpt(tokens: Token[]): string {
  const text = plainText(tokens);
  if (text === "") {
    throw new MarkdownPolicyError("empty_text");
  }
  // Array.from iterates Unicode code points — the same unit Python len() counts.
  const chars = Array.from(text);
  if (chars.length <= MAX_EXCERPT_CODEPOINTS) {
    return text;
  }
  let prefix = chars
    .slice(0, MAX_EXCERPT_CODEPOINTS - 1)
    .join("")
    .replace(/\s+$/u, "");
  if (!/\s/u.test(chars[MAX_EXCERPT_CODEPOINTS - 1] ?? "")) {
    const boundary = prefix.lastIndexOf(" ");
    if (boundary >= MAX_EXCERPT_CODEPOINTS / 2) {
      prefix = prefix.slice(0, boundary).replace(/\s+$/u, "");
    }
  }
  return `${prefix}…`;
}

export function projectSafeMarkdown(
  source: string,
  rendererVersion: string = RENDERER_VERSION,
): SafeMarkdownProjection {
  if (rendererVersion !== RENDERER_VERSION) {
    throw new MarkdownPolicyError("unsupported_renderer");
  }
  const { md, tokens } = parse(source);
  md.renderer.rules.link_open = (linkTokens, index, options, env, self) => {
    const destination = linkTokens[index]?.attrGet("href");
    if (typeof destination === "string" && !destination.startsWith("#")) {
      linkTokens[index]?.attrSet("rel", "nofollow noopener noreferrer");
    }
    return self.renderToken(linkTokens, index, options);
  };
  return {
    description_format: DESCRIPTION_FORMAT,
    renderer_version: RENDERER_VERSION,
    html: md.renderer.render(tokens, md.options, {}),
    excerpt: excerpt(tokens),
  };
}

/** Render passport description HTML; falls back to escaped plain text. */
export function renderPassportDescription(source: string): string {
  try {
    return projectSafeMarkdown(source).html;
  } catch {
    const escaped = source.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    return `<p>${escaped}</p>\n`;
  }
}
