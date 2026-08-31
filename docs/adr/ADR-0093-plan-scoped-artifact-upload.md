---
description: "Decision to bind publication bytes through a plan-scoped upload rather than retrieval from Git."
last_verified: "2026-08-15"
---

# ADR-0093: Plan-scoped upload of artifact bytes

Status: accepted.

## Context

The publication plan already carries the exact `content_digest`, and public
version reads can return the bytes. The write side is absent: `ObjectLocation`
is created only in tests, and confirm does not verify that the bytes are in the
store. The catalog can show metadata without immutable content. `#312` requires
one constrained authenticated path for binding bytes to the plan before
confirm.

Two paths were proposed: upload into the plan, or server-side retrieval from
public Git at an exact 40-hex commit and subpath. Both satisfy the issue. They
cannot both be implemented: two writers will diverge in packaging and failure
behavior.

## Options

1. The server clones public Git at the declared commit and packages the subpath.
   This requires no separate upload client, but brings network access, git,
   packaging, and the repository-content attack surface into confirm.
2. The author uploads already packaged bytes to the plan. The server checks the
   digest and size, validates the archive for traversal and special files, and
   writes to the existing immutable object store. Git remains the passport
   source, not the byte store.
3. Presigned PUT to RustFS. The client bypasses the API, the storage key ceases
   to be opaque, and `REQ-2004` is broken.

## Decision

Option 2 is accepted.

The route is an authenticated `PUT` on the plan with an
`application/octet-stream` body. The digest and size come from the plan, not a
client header. Confirm reads the store and rejects the request if the bytes are
absent. Publish creates an `ObjectLocation` for the content-addressed object
already present. Repeating identical bytes is idempotent. A different digest
under the same `X.Y` remains a rejection under `REQ-2606`.

This decision does not enable retrieval from Git or a presigned URL.

## Consequences

- one new `/v1` route appears; the CLI upload client is a separate track;
- worker `upload` is not this route: the API writes synchronously so that
  confirm sees the bytes without racing the queue;
- the size limit and zip parsing belong to the same layer as safety unpack;
- switching to Git retrieval requires a new ADR and separate packaging.

## Reconsideration conditions

The decision is reconsidered if the measured artifact size no longer fits in a
synchronous upload, or if Git itself without local packaging becomes the only
permitted byte source. Upload then remains, while retrieval is introduced as a
separate route, not as a second writer for the same digest.
