---
description: "Versioned safe CommonMark profile for immutable version descriptions."
last_verified: "2026-08-09"
---

# ADR-0063: Versioned Safe Markdown Descriptions

Status: accepted.

## Context

The passport is already the sole description of an exact version. Plain text is safe,
but insufficient for a lengthy explanation of the setup composition; arbitrary Markdown without
a shared parser/render contract produces different results in the CLI, API, and web interfaces and
reintroduces HTML, image, and URL injection.

The number `ADR-0049`, proposed in an earlier issue, already canonically belongs to
HarnessBundle. The new decision receives the next available number, `ADR-0063`, without
rewriting history.

## Decision

The `description` field remains the sole content field and part of the exact
version passport. In passport schema v1, it always means `commonmark_v1`;
the safe projection explicitly returns the format and renderer version. Thus,
the passport does not acquire a second field, and historical content-addressed bytes do not
change due to a materialized default.

`commonmark_v1` is implemented using a CommonMark parser with raw HTML disabled and a closed
allowlist of token types. The input must additionally be NFC/LF, fit within
16 KiB and 256 lines, and contain no control characters. Images are prohibited entirely.
Links are permitted only if they are absolute `https` links without credentials or local fragments.

The `safe_markdown_v1` renderer builds HTML only from the accepted token tree. External
links receive `rel="nofollow noopener noreferrer"`; source HTML is not
sanitized after the fact, but rejected before rendering. A separate deterministic
excerpt projection extracts text and inline code, collapses whitespace, and is limited to
240 Unicode code points.

Positive, boundary, and malicious cases belong to a single JSON corpus in
the contracts package. The Python validator and future web renderer must read it as
a single source rather than maintain independent lists of examples.

## Considered Alternatives

1. Store plain text. Rejected: it does not satisfy the product requirement to describe complex
   setups.
2. Sanitize arbitrary HTML after rendering. Rejected: parser differentials
   and sanitizer changes create a hidden second semantics.
3. Store Markdown and HTML simultaneously. Rejected: two mutable copies diverge
   and change the digest independently.
4. Load remote images through a proxy. Deferred: this is a separate media/security
   system and is unrelated to the version description.

## Compatibility

Passport schema v1 always undergoes full `commonmark_v1` validation. An unknown
format or renderer fails closed. Any incompatible change to the grammar,
limits, HTML, or excerpt receives a new version, preserving the old renderer for
historical passports.

## Consequences

The description becomes expressive and identically verifiable by both humans and agents,
but every consumer must implement the exact corpus. Remote images and raw HTML
are impossible even for a trusted author. Correcting published text requires
a new version, like any other passport change.

## Reconsideration Conditions

The decision will be reconsidered if media attachments, localized
descriptions, or a new CommonMark profile are needed; none of these cases automatically adds
a mutable object-level description.
