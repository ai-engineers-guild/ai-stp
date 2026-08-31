---
description: "Decision to store component presentation separately from the immutable passport and deliver media securely."
last_verified: "2026-08-10"
---

# ADR-0075: Component media gallery and reactions

Status: accepted.

## Context

The immutable version passport already owns the source repository and technical facts,
but the gallery, preview choice, and like change independently. Including them in the passport
would create a new component version with every presentation change.

## Decision

Store component presentation as a revisioned object-level projection with no more than
five ordered media records. Owner upload goes through
`POST /v1/owner/objects/component/{stable_id}/presentation/media` (allowlist:
JPEG/PNG/WebP/GIF/MP4/WebM up to 25 MiB) and is served as
`/v1/media/component/{media_id}`; a GitHub reference is pinned to a commit SHA;
YouTube is represented by a validated ID. The preview is set explicitly with `position = 0`.
The public catalog joins only the ready projection.

Individual likes are stored as a separate unique reaction `(account_id, object_kind,
stable_id)`, while `catalog_metadata.likes_count` remains the public aggregate.
Reports remain in the existing report-case workflow.

## Consequences

Media/presentation/reaction tables, an owner mutation API, and a worker job for
normalization are required, along with a cache policy for signed URLs, a public gallery
projection, and a web editor. Deleting media first removes it from the projection, then
asynchronously deletes the blob after the retention window.

## Reconsideration Conditions

The decision will be reconsidered if an in-house video streaming service, a media
moderation service, or a legal obligation to retain source files longer emerges.
