---
description: "Decision to make the revision identifier content-addressed: revision_ plus the 64-hex hash of canonical data in the revision domain."
last_verified: "2026-08-05"
---

# ADR-0036: Content-addressed revision identifiers

Status: accepted.

## Context

`canonical-data.md` and `SPEC-015` REQ-1502 define a revision as content-addressed: identical canonical data must produce the same identifier on every device, which underpins synchronization idempotency and the parent graph. The first foundation implementation nevertheless included `revision` in the logical stable-ID registry and minted a random ULID. The document and code contradicted each other, and the first persisted passport would have established random identifiers where deterministic ones are required.

The passport-envelope example already shows the `revision_...` form without fixing the suffix, and the `ai-stp:revision:v1` domain exists in the hash-domain list.

## Options

1. Keep a random ULID. Simple, but breaks content addressing: two devices assign different identifiers to the same bytes, and replaying an event creates a second revision.
2. Use bare `sha256:<hex>` as the revision identifier. Deterministic, but visually indistinguishable from other hashes and inconsistent with the envelope example.
3. Use a typed content wrapper: `revision_` plus 64 hexadecimal characters from the hash of the revision's canonical data in the `ai-stp:revision:v1` domain.

## Decision

Option 3 is accepted.

**A revision identifier is derived, not issued.** `revision_id = "revision_" + hex64(sha256("ai-stp:revision:v1" || 0x00 || canonical revision bytes))`. Identical content produces the same identifier on every device; changing one field changes the identifier.

**No random path exists.** The `revision` prefix is excluded from the logical stable-ID registry; attempting to mint a random revision identifier fails closed. The grammars of the two identifier kinds do not overlap: a stable ID suffix is a Crockford ULID, while a revision suffix is lowercase hex.

**One type serves all consumers.** `parent_revision_ids`, the synchronization event, and `EntityRevision` use this same type; the schema carries the `^revision_[0-9a-f]{64}$` pattern.

## Consequences

- foundation receives a revision-identifier derivation and validation module with no random-generation path;
- `canonical-data.md` establishes the exact suffix form;
- future passport-envelope and synchronization-event schemas reference one pattern;
- no revisions have yet been written, so no migration is required.

## Reconsideration conditions

This decision will be reconsidered if interfaces need a shortened identifier form; a display abbreviation will then be added, not a second canonical format.
