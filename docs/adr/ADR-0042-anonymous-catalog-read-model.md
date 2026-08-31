---
description: "Decision on the anonymous public catalog read model: opaque cursor, resistance to enumeration, and the object-byte delivery mechanism."
last_verified: "2026-08-06"
---

# ADR-0042: Anonymous Catalog Read Model and Object-Byte Delivery

Status: proposed.

## Context

`#81` (`SPEC-021`) implements the first anonymous public catalog: search, listing,
and exact object and version reads for the web and CLI without user publication.
The wire contract was frozen by `#71` in `schemas/v1/openapi.json` and the
`ai_stp_contracts.catalog` models: six `GET` routes under `/v1/catalog/components`
and `/v1/catalog/setups`, an opaque `Cursor` with a pattern and page boundary,
`authoritative` and `experimental` sections, a prohibition on revealing a hidden
object, and a published-passport requirement. The `catalog_metadata` and
`object_location` storage schema was created by `#79` (`SPEC-020`); the immutable
object-storage adapter with digest and size validation already exists; trust lanes
were accepted by `ADR-0016`; verification integrity is governed by `ADR-0026` and
`ADR-0032`.

The contract establishes the response shape but not the mechanism. Three decisions
are not selected by any accepted ADR; without them, the catalog slice would diverge
into incompatible implementations, and some cannot be rolled back without changing
wire behavior:

1. how to construct the opaque cursor so that ordering is total, stable, and
   tamper-resistant, while a page from one cursor sequence covers both trust lanes
   without duplicates or omissions;
2. how to guarantee that hidden, private, and draft records cannot be enumerated
   through several independent channels, rather than through a single flag;
3. how to deliver artifact bytes after object and action validation: an API-mediated
   stream or a short-lived restricted URL.

The storage schema does not contain `published_at`, the trust lane, or verification
axes: `#79` intentionally kept the columns minimal. The frozen contract's card
projections require these values, so the decision also affects a small additive
schema extension.

## Options

Opaque cursor:

1. A signed HMAC token that encodes the filter and sort signature and the exclusive
   last key `(sort_key..., stable_id)`. Keyset pagination using row-tuple comparison
   (`tuple_(...) > (...)` in `SQLAlchemy 2`) provides a total stable order with
   `stable_id` as the tie-breaker; the signature detects tampering; binding to the
   filter signature detects moving a cursor to a different filter; the page limit
   applies across both lanes in total. The cost is a signing secret in the
   environment and cursor invalidation when the filter changes, which is the correct
   behavior.
2. Offset pagination with an encoded offset. Simpler, but unstable under insertions
   between pages (duplicates and omissions), while an "opaque offset" can be decoded
   and allows selecting an arbitrary slice. Does not satisfy `REQ-2105`.
3. A stored server-side cursor (one state row per listing). Eliminates the signature,
   but introduces state, lifetime, and cleanup for an anonymous route and opens an
   enumeration channel through the cursor identifier. The cost exceeds the benefit.

Resistance to enumeration:

1. A set of independent protections for every channel: the same `AI_STP_NOT_FOUND`
   for a missing and a non-public record; no collection count on the wire (already in
   the contract); a projection and error path of the same shape regardless of whether
   a hidden record exists; an opaque object key without authority (already in `#79`).
   Every channel is closed separately and secured by a test.
2. A single visibility flag in the row query. Cheap, but leaves count, timing, and key
   channels open; a single flag would conceal the fact that the channels are
   independent.

Object-byte delivery:

1. API-mediated streaming (`StreamingResponse`): the server is both the authorization
   point and the data path; object and action validation runs on every request, the
   client never accesses storage directly, and the object key never leaves the
   server. The cost is traffic through the application.
2. A short-lived restricted presigned URL: the server authorizes once and issues a
   signed URL with a short TTL and least privilege; storage serves the bytes directly.
   A presigned URL is a bearer artifact: any holder can use it until expiration, and
   `RustFS`/`S3` are not exposed to the internet under `SPEC-019`, so direct external
   client access to storage is unavailable.

## Decision

A signed HMAC keyset cursor, a set of independent enumeration protections, and
API-mediated object-byte delivery are accepted for Sprint 1.

Cursor:

- The token encodes the cursor-schema version, the active filter and sort signature,
  and the exclusive last key `(sort_key..., stable_id)`; it is serialized compactly
  and conforms to the frozen `CURSOR_PATTERN` from contract `#71`
  (`^[A-Za-z0-9_-]{1,512}$`).
- Ordering is defined by server-side sorting with `stable_id` as the final tie-breaker;
  page advancement uses keyset comparison of the row tuple, not `OFFSET`.
- The HMAC signature is computed with a secret from the environment (not a secret in
  code, like `secret_key` in `ADR-0041`); an invalid signature or filter-signature
  mismatch produces a typed invalid-request error.
- Both trust lanes share one cursor sequence; the page is limited across both lanes
  in total by `PAGE_SIZE_MAX`.

Resistance to enumeration is a set of per-channel protections: one
`AI_STP_NOT_FOUND`, no counts on the wire, a response and error shape independent of
whether a hidden record exists, and an opaque object key without authority; each is
secured by a test.

Bytes are delivered through an API-mediated stream: object and action validation run
on every request, followed by a `StreamingResponse` from the object-storage adapter
with digest and size validation before delivery. Presigned URLs are not used in
Sprint 1 because storage is not exposed and the URL's bearer semantics require
separate justification.

Publication state: `published_at`, the trust lane, and verification axes are added by
a small additive storage-schema extension (a forward migration under `SPEC-020`),
optional-first; ownership of the storage layer remains with `SPEC-020`, while value
semantics remain with `SPEC-021` and `ADR-0016`/`ADR-0026`.

## Consequences

- The `catalog` slice in `apps/api` follows `ADR-0037`; the shared core gains a
  cursor parsing and issuance dependency and a public-visibility validation
  dependency shared by listing and read routes.
- A cursor-signing secret from the environment is required; it is not a secret in
  code and is documented without a value in environment examples.
- A small additive schema migration for publication state is required; it follows
  the rules of `SPEC-020`, does not redefine its ownership, and does not modify the
  shared wire schemas from `#71`.
- The card projection reads `latest_*` fields from the passport of the latest
  proposed version; the absence of a publisher field in the frozen `#71` card is
  recorded as a discrepancy with the issue prose and, if necessary, addressed by an
  additive request to `#71`, not by a local field.
- In Sprint 1, without a validation pipeline, no object carries
  `component_verified`, so the entire seed is experimental and the `authoritative`
  lane is legitimately empty; this is a direct consequence of
  `ADR-0016`/`ADR-0026`, not a defect.
- Required tests: a property test for ordering and the cursor; rejection of tampered
  and foreign cursors; resistance to enumeration through every channel; digest and
  size validation during delivery; seed idempotency; and a `run_conformance` run.
- Rollback: the cursor mechanism and delivery path are encapsulated in the slice and
  shared core; switching to a presigned URL requires a new ADR because it changes the
  access model and is not performed in place.

## Reconsideration Conditions

The decision will be reconsidered if byte-traffic volume makes the API-mediated path
a bottleneck and there is readiness to accept the bearer semantics of a presigned URL
with a short TTL and least privilege; if a byte-delivery route appears in contract
`#71` that requires a different form; or if multi-region reads without a shared
signing secret require a different cursor scheme.
