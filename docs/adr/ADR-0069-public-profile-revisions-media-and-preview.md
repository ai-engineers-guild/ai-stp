---
description: "Decision to store the public profile as revisions and isolate its media/preview."
last_verified: "2026-08-08"
---

# ADR-0069: Public Profile Revisions, Media, and Preview

Status: accepted.

## Context

ADR-0023 separated PublicProfile from DeveloperPassport, but the current API has
no scenario for reading and writing the profile, the publisher page relies on
fixtures, and the OAuth avatar exists only on the linked identity. Draft preview,
a dedicated avatar, and prevention of provider identity/media originals leakage
are required.

## Alternatives

1. Produce the profile from account/OAuth claims. This is quick, but violates
   ADR-0023 and changes the public page without an explicit decision by the
   author.
2. Store a single mutable public record. This requires fewer tables, but preview
   has no stable basis, and audit/rollback are not reproducible.
3. Store immutable profile revisions with a draft/publish lifecycle and separate
   processed media assets.

## Decision

Alternative 3 is accepted according to SPEC-028. The public profile has an
owner-scoped draft, one published revision, and a content digest. Preview is
built from the same sanitized projection as the public route, but authorization
does not allow it to become a public URL. The avatar is never a provider URL:
the selected OAuth image or owner upload undergoes server-side
normalisation/quarantine and is stored in RustFS/S3 as a restricted processed
asset.

## Consequences

- Profile/media tables, owner/public API scenarios, migrations, audit, a
  generated client, and redaction tests are required.
- The Upload API is limited to avatar media; artifact object-store semantics
  are not silently expanded.
- Publish requires an ETag, idempotency, preview confirmation, and a digest
  recheck.
- Existing initial profiles are migrated into revisions; the fixture projection
  must not remain the production implementation.

## Reconsideration Conditions

The decision will be reconsidered if the profile becomes a shared organization
object, non-image media are introduced, or legally mandatory profile review is
required.
