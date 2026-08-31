---
description: "SPEC-029: Immutable safe Markdown descriptions for versions."
last_verified: "2026-08-09"
---

# SPEC-029: Immutable safe Markdown descriptions for versions

## Purpose

Give components and setups expressive descriptions without a second mutable
documentation source, divergence between CLI, API, and web, or the ability to
execute or covertly load untrusted content.

## Scope

Included are the `description` field of an exact version passport, the
`commonmark_v1` format, validation, safe HTML, a text excerpt, and a shared
malicious corpus. A separate object-level text, a WYSIWYG editor, arbitrary
HTML, remote images, and attachment uploads are excluded.

## Terms

- `commonmark_v1` — a closed CommonMark profile with versioned limits and
  prohibited constructs;
- `safe_markdown_v1` — the validator and renderer version;
- excerpt — a deterministic single-line text projection for a card.

## Requirements

- `REQ-2901`: The only substantive version-description field is `description`
  in the immutable `ComponentVersionPassport` or `SetupVersionPassport`; there
  is no separate mutable documentation field.
- `REQ-2902`: For passport schema v1, `description` always means
  `commonmark_v1`; the render projection explicitly declares the format and
  renderer version, while the exact source is included in the canonical bytes
  and passport digest.
- `REQ-2903`: Input must be non-empty UTF-8 in Unicode NFC, use LF only, occupy
  no more than 16 KiB, and contain no more than 256 lines.
- `REQ-2904`: The profile permits paragraphs, headings, emphasis, inline code,
  fenced code blocks, block quotes, thematic breaks, ordered and unordered
  lists, and links using only `https` or local fragment links.
- `REQ-2905`: Raw HTML, images, unsafe or ambiguous URLs, control characters,
  and unknown token types fail closed before the version is stored.
- `REQ-2906`: `safe_markdown_v1` produces deterministic sanitized HTML without
  raw source HTML; an external link receives
  `rel="nofollow noopener noreferrer"`.
- `REQ-2907`: The excerpt is extracted from text and code tokens, collapses
  whitespace, is limited to 240 Unicode code points, and ends truncated text
  with `…`.
- `REQ-2908`: API, CLI, and web use one versioned positive/malicious corpus; any
  difference in accepted/rejected results, HTML, or excerpt is a contract
  failure.
- `REQ-2909`: Changing the description of a published version does not rewrite
  the passport and creates a new `X.Y` version under the general registry rules.
- `REQ-2910`: An unsupported `description_format` or renderer version is not
  silently downgraded and returns a typed incompatibility.

## States and errors

A description is either accepted in full or the version is not created.
Partially sanitized input is not stored. A profile violation is an invalid
passport; an unknown format or renderer version is an incompatibility, not an
empty description.

## Security and privacy

The renderer does not execute code, permit HTML, or load resources. URLs are
checked after CommonMark parsing; percent-encoding, entity decoding, and Unicode
must not turn a prohibited scheme into an allowed one. Limits are applied before
expensive parsing.

## Compatibility and migration

Before the public release, old passports without `description_format` are read
as `commonmark_v1` only if their `description` passes the current profile; the
next serialization includes the field explicitly. Published bytes are not
rewritten after release. A change to grammar, limits, HTML, or excerpt creates a
new format or renderer version.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-2901` | A contract test proves that the passport and local object have no second description field. |
| `REQ-2902` | Changing description changes the canonical passport digest, while the projection contains the exact format and renderer version. |
| `REQ-2903` | The boundary corpus covers bytes, lines, NFC, CR, and control characters. |
| `REQ-2904` | The positive corpus compares exact HTML and excerpts for every permitted construct. |
| `REQ-2905` | The malicious corpus rejects HTML, images, unsafe URLs, controls, and an unknown token. |
| `REQ-2906` | Golden HTML contains no source HTML and fixes the safe link attributes. |
| `REQ-2907` | Golden excerpts cover whitespace, Unicode, and the exact 240-code-point boundary. |
| `REQ-2908` | A Python contract test validates every record in the shared JSON corpus; the web owner consumes the same file without a copy. |
| `REQ-2909` | A registry test rejects replacing the bytes of a known version and accepts a new minor version. |
| `REQ-2910` | Unknown format and renderer versions produce a typed incompatibility. |
