---
description: "HTTP API versioning, authorization, idempotency, and concurrency."
last_verified: "2026-09-04"
---

# HTTP API

## Field ownership

Exact request and response fields belong to the generated schemas in `schemas/v1` and the `packages/contracts` models that produce them. The route list, parameters, and response codes belong to the generated `schemas/v1/openapi.json`; it is built from the same models by the same command and checked by the same gate, so the two published halves of the contract cannot diverge.

This document owns what neither schemas nor OpenAPI can express: header semantics, rules for opaque values, concurrency behavior, and what the API intentionally does not promise. Fields and routes must not be duplicated here, because the copy would drift from its source.

## General rules

The MVP base path is `/v1`. The client sends and receives UTF-8 JSON. Every response contains a request identifier; a mutating operation also returns `operation_id`.

## Headers

| Header | Purpose |
|---|---|
| `X-Request-Id` | Request identifier of the form `request_<ULID>`. Minted by the client and echoed by the server; if absent or malformed, the server mints its own. |
| `X-Operation-Id` | Mutating-operation identifier of the form `operation_<ULID>`. Present only in mutation responses. |
| `X-AI-STP-Schema-Version` | Major wire-schema version. An unknown major version is rejected with `AI_STP_SCHEMA_UNSUPPORTED`, not defaulted. |
| `Idempotency-Key` | Required for creation and mutation. Form: 16 to 128 characters from `A-Za-z0-9._~-`. The client selects the value; it is opaque to the server. |
| `If-Match` | Update and revocation precondition using an `ETag` or expected revision. |
| `ETag` | Current resource version for a subsequent `If-Match`. |

## Page and cursor

A cursor is opaque: it is a position in an ordering, not an offset or identifier. Its form is 1 to 512 characters from `A-Za-z0-9_-`. The client returns it verbatim and does not parse it.

The cursor sequence follows the selected sort, including direction, and
enumerates the complete set: an object appears on exactly one page, and
pagination does not change the resulting set. Cursor keys are those sort keys
plus `stable_id`. Page mode uses the same order before `OFFSET`/`LIMIT` and may
return `total_items` for the already authorized public slice. Equivalent
filters share a signature: `q` is trimmed and blank is absent; multi-value
parameters are unique and sorted; singular `harness_id`/`component_type` merge
with their list forms using OR (`REQ-2105`, `ADR-0151`).

The default page size is `20`, with a maximum of `100`; a request above the maximum is clamped rather than rejected. The same maximum limits the number of objects in the response, not merely the declared size, or one “page” could return the entire catalog.

`next_cursor` is always present and is `null` on the last page. This applies to catalog pages and other object lists. A private server-outbox pull page belongs to `sync-event.md`: a nonempty page returns the cursor of the last sequence emitted even when no more rows exist in that read. The total object count is never returned, because it would reveal objects the caller is not authorized to read.

Catalog search accepts an optional `updated_from` / `updated_to` window as `YYYY-MM-DD` calendar dates. Semantics are inclusive in UTC: the lower bound is `updated_at >=` the start of the specified UTC day, and the upper bound is `updated_at <` the start of the following UTC day. One bound is allowed. If both are set and `from > to`, the request is rejected with `AI_STP_VALIDATION_ERROR`. Existing cursors without this filter remain valid: empty bounds are not included in the filter signature.

Sort direction is part of the server ordering and filter signature. The server
applies `asc` or `desc` before computing the page boundary; the client must not
simulate direction by reversing a single received page.

The `unspecified` sentinel does not mean the same thing for both relationship filters. In the service facet it selects an object with no associated service. In the country facet it selects an object associated with a service that has no country code. An object without a service does not by itself match the country filter. Facets combine with AND; values within a facet combine with OR. Singular `service_domain` and `country_code` are accepted and merged with the lists. The cursor signature includes both sets and the date window, so a cursor from one selection is invalid for another.

Results are separated into sections rather than mixed: `experimental` lane candidates are returned in a separate response array and only when the request carries consent under `SPEC-006` REQ-603. Both sections share one cursor sequence, so traversal still neither repeats nor skips an object, and the page limit applies to the sum of both sections rather than each separately.

## What the API intentionally does not promise

Exact-version bytes are served by a separate artifact route as an `application/octet-stream`, not JSON. The storage object key is not given to the client and is not authorization under `SPEC-020` REQ-2004: the route is the sole entry point. Presigned URLs are deferred until measured need and a separate ADR.

Binding bytes to a publication plan is a separate authenticated upload to the plan itself, not a Git read or a public store write. Confirm is rejected without durable bytes whose digest matches the plan (`ADR-0093`).

The client validates received bytes against the version **passport**, not the response: headers from the server that supplied the bytes cannot attest to them, while the passport is a versioned content-addressed description the client already holds. The passport declares the digest and size and is the only independent expectation in this chain. Without it, the public catalog remains a showcase rather than an installation source.

The response is streamed and aborted as soon as more than the declared size arrives. The artifact is the only payload here without a modeled upper bound; otherwise the server or anything between it and the client could send unlimited data that the client would retain in full.

Public version numbers are not contiguous. Hiding a version does not free its number: under `SPEC-005`, only state changes and bytes remain. Thus `1.0, 1.2` is a valid response; the gap at `1.1` proves nothing and is not grounds for action. Pagination does not conceal this, and omitting publication time would sacrifice useful information for one bit, so the contract declares non-contiguity instead of pretending to enumerate a dense sequence.

## Errors

An error has a stable code, safe message, retryability marker, request identifier, and bounded details. Validation, authentication, authorization, conflict, rate limiting, unavailable dependency, and internal errors are distinct.

The error body matches the CLI error envelope in `cli-json.md`: one reader parses both cloud and local failures. A successful response carries the resource itself; success is already conveyed by the status code.

The stable-code-to-status-code mapping is closed and derived from the completion class; exceptions are listed explicitly:

| Status code | Stable codes |
|---|---|
| `400` | `AI_STP_VALIDATION_ERROR`, `AI_STP_UNSUPPORTED_APPLY`, `AI_STP_SCHEMA_UNSUPPORTED`, `AI_STP_AUTHORIZATION_PENDING`, `AI_STP_AUTHORIZATION_EXPIRED`, `AI_STP_AUTHORIZATION_DECLINED`, `AI_STP_SEO_FACTS_INVALID`, `AI_STP_SEO_OUTPUT_INVALID` |
| `401` | `AI_STP_AUTH_REQUIRED` |
| `403` | `AI_STP_PERMISSION_DENIED`, `AI_STP_DEVICE_REVOKED` |
| `404` | `AI_STP_NOT_FOUND` |
| `409` | `AI_STP_CONFLICT`, `AI_STP_PLAN_STALE`, `AI_STP_USER_DECISION_REQUIRED`, `AI_STP_SEO_SOURCE_STALE` |
| `412` | `AI_STP_PRECONDITION_FAILED` |
| `429` | `AI_STP_RATE_LIMITED` |
| `500` | `AI_STP_PARTIAL_OPERATION`, `AI_STP_CATALOG_INTEGRITY`, `AI_STP_INTERNAL`, `AI_STP_SEO_RENDER_FAILED` |
| `503` | `AI_STP_DEPENDENCY_UNAVAILABLE`, `AI_STP_SEO_ENRICHMENT_UNAVAILABLE` |
| `504` | `AI_STP_TIMEOUT_UNCONFIRMED` |

The three device-flow states share `400` under RFC 8628, but each retains its own stable code: a shared status code does not collapse distinct outcomes; `code` remains the machine identifier.

`AI_STP_CATALOG_INTEGRITY` applies to a reachable published record that fails its own integrity validation under `SPEC-021` `REQ-2108`. It is not `AI_STP_NOT_FOUND`: the object exists and is public, and claiming it is absent would send the client elsewhere to find something already present. It is not `AI_STP_INTERNAL` either: the condition is diagnosable, has a recovery path, and requires separate operator alerting. Retrying does not change the outcome—the stored bytes will not become valid between attempts—so the client does not retry this code despite `500`.

The `passport` field in an exact-version response is the stored published document from which `passport_digest` was computed. Reserializing it through the current model, which inserts later-added fields with default values, changes the bytes and breaks validation. This does not violate the “all declared response fields” rule: the response envelope is complete, while the passport is an immutable snapshot.

API groups cover authentication, devices, profiles, the registry, private drafts, synchronization, publication, grants, reports, and minimal administrative actions. The web interface does not use hidden routes unavailable to the CLI without a separate security reason.

## Rate limiting

One node maintains two independent sliding windows for every HTTP request before the route handler: a process-wide budget (default 100 requests per 60 seconds) and a budget per client address (default 1000 requests per 3600 seconds). Method and route template are not part of the key. The address is `X-AI-STP-Client-IP` when it parses as an IP address, and the transport peer's `request.client.host` otherwise. That header is stated by the edge proxy with `proxy_set_header`, which replaces whatever the client sent (`ADR-0135`); `X-Forwarded-For` and `Forwarded` are still not read. A key whose window is empty releases its slot. New visitors do not converge into one shared overflow bucket. Rejection by one window does not consume the other. Exceeding a limit returns `AI_STP_RATE_LIMITED` and sets `Retry-After`. Missing environment variables retain these values rather than making limits unlimited; explicit `0` disables only that dimension. A distributed limiter, Redis, SlowAPI, and rate limiting in the edge proxy are not promised (`ADR-0128`).

## Authorization

A session or token authenticates the account, but every action additionally checks ownership, an active grant, and administrative authority. An object identifier, address, or storage key does not grant access.

## Mutations

Creation and mutation require `Idempotency-Key`. Device authorization initiation carries this key in the `idempotency_key` body field, as does device revocation: the route creates state, and the client must be able to retry without receiving a second authorization. The client selects the value once per logical initiation and repeats it on every transport attempt; the server must store the request fingerprint with the result and answer a retry using the same key with the same `device_code`, without creating a second record. The same key with a different body is a conflict. Updating an existing entity uses `If-Match` with an ETag or expected revision. A conflict returns the current version value without silent overwrite.

A failed precondition and a concurrent change are distinct: the former yields `AI_STP_PRECONDITION_FAILED` with `412`, the latter `AI_STP_CONFLICT` with `409`. A shared status code would make them indistinguishable, while the required client actions differ: rereading and retrying is sufficient for the first, while the second requires a decision.

## Lists

Lists use an opaque cursor and stable ordering. Ordering is complete and stable within one cursor sequence: traversal neither repeats nor skips an object. A deleted or hidden object is not leaked through a count, search, or direct cursor.

## Object storage

The client receives no persistent RustFS/S3 authority. Artifact download or upload occurs through a validated server process or a short-lived restricted link after the object and action are checked.

## Compatibility

A breaking change receives a new API or schema version. An added field is optional at first. The supported window of older CLI versions is declared and tested with mixed contract tests before old behavior is removed.

A wire object carries all declared fields—keys are never absent and an optional value is sent as `null`—while allowing added optional fields within the supported major version. The reader preserves rather than discards them; otherwise an installed CLI would break on exactly the evolution path prescribed by `schema-evolution.md`, recoverable only through a forced upgrade.

The rule applies to responses and **does not apply to requests**: an unknown request parameter is rejected. A response is a description; a request is an instruction. A silently ignored filter is not compatibility: the caller asked to narrow results, the server did not, and the response appears complete. A typo in a filter name must produce a typed error, not the entire catalog. Version mismatch is carried by `X-AI-STP-Schema-Version`, which rejects explicitly rather than pretending the instruction was understood.
