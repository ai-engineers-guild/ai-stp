---
description: "A reachable published record that fails integrity verification returns a distinct code, not absence."
last_verified: "2026-08-24"
---

# ADR-0079: Catalog corruption is not absence

Status: accepted.

## Context

`SPEC-021` `REQ-2108` requires passport bytes to be checked against
`passport_digest` before responding and a conflict to be rejected with a typed
error and no partial response. The check exists: `verify_passport_integrity`
verifies the digest, revision seal, public visibility, and identity and raises
`CatalogIntegrityError`.

The read layer converted this error to `CatalogNotFound`, and the router then
converted it to `AI_STP_NOT_FOUND` with status code `404`. The typed-error
requirement was formally satisfied, but the selected type meant "the object
does not exist," even though the row existed and was public and reachable.

The consequences were observed on the real chain in `#254`: the publication
plan reached `published` with `component_verified=true`, after which the public
catalog returned `404`. The poisoned immutable version was indistinguishable
from an ordinary miss, and its state was discovered only through a manual
database inspection. Republishing the same `X.Y` is impossible because of
immutability, and the rejection reason was recorded nowhere.

The other half of the same problem was a structurally invalid passport. It did
not reach the integrity checks: `model_validate` inside
`verify_passport_integrity` raised `pydantic.ValidationError`, which is not a
`CatalogIntegrityError` and was caught by none of the four readers. One cause
produced two outcomes: a silent `404` for some checks and an unhandled `500` for
schema parsing.

The `write` axis of this problem is addressed separately: create, confirm, and
worker use one canonical validator, `passport_digest` is separate from the
artifact digest, and transition to `published` is atomic with projection
storage. This ADR closes the `read` axis: how the system responds to an already
corrupted record.

## Options

**Keep `AI_STP_NOT_FOUND`.** It costs nothing and fixes nothing. The client is
told to look elsewhere for something that is present; the operator receives no
signal; corruption continues to look like an ordinary miss. This exact behavior
hid `#254`.

**Use `AI_STP_INTERNAL`.** It is honest about the status code and needs no new
entry in the closed registry. But `AI_STP_INTERNAL` covers any unhandled error,
so alerting on it cannot distinguish a diagnosable data defect with a known
recovery path from an arbitrary failure. The operator loses precisely the
signal for which the record is verified.

**A distinct `AI_STP_CATALOG_INTEGRITY` code.** This requires an entry in the
closed registry, schema regeneration, and client coordination. In return, the
condition becomes independently observable and independently actionable.

## Decision

A reachable published record that fails integrity verification returns
`AI_STP_CATALOG_INTEGRITY` with status code `500`.

- The code is added to the closed `ERROR_CODES` registry with the `EXIT_INTERNAL`
  exit class and `report_bug` handling: this is a server defect, not a request
  defect, and the agent must report it rather than change or retry its call.
- The read layer raises `CatalogCorrupt`, not `CatalogNotFound`. The types are
  deliberately unrelated by inheritance: making one a subtype would render
  them indistinguishable to any caller that catches the parent.
- Every rejection writes an `error`-level event containing the reason, object
  kind, `stable_id`, and version. The client response carries no details, so
  the log is the only place where the reason exists.
- `pydantic.ValidationError` is converted to `CatalogIntegrityError` inside
  `verify_passport_integrity`. One cause leaves the function through one door,
  and no caller needs to know about pydantic.
- The client does not retry this code despite `500` being among retryable
  statuses: stored bytes do not become valid between attempts.
- The byte-delivery route follows the same rule. Its docstring explicitly
  acknowledged merging three states into one: "absent, inaccessible, **or fails
  its integrity boundary**". A declared digest or size mismatch with storage,
  an unparsable passport, a missing artifact section, and a dangling object
  reference now raise `ArtifactCorrupt`, not "not found": the bytes exist and
  disagree with their passport, and calling them absent is exactly what
  `REQ-2108` forbids. Both operations declare the code in the contract.

Anti-enumeration remains intact on both routes. A private or absent object still
returns `404` because it fails the public-visibility filter; only a publicly
reachable corrupted object receives the distinct code—the object already
visible in search.

Search routes return the same `AI_STP_CATALOG_INTEGRITY` as detail. Skipping a
corrupted row would change page completeness and ordering stability under
`REQ-2105` and reachability under `REQ-2106`. An unhandled `AI_STP_INTERNAL`
would hide the same diagnosable cause that detail already names.

The revision seal is checked against the stored document, not against
`model_dump` after validation. Fields that the model later acquired with
default values are not part of the historical seal: a round trip through the
model adds them and would reject every previously published record whose digest
over the stored bytes still matches.

## Consequences

`AI_STP_CATALOG_INTEGRITY` appears in `error-code.schema.json`, in CLI machine
help, and in the `500` response description for the four catalog read routes in
`schemas/v1/openapi.json`. Consumers that enumerate codes as a closed list must
recognize it; the CLI client already lists it as non-retryable.

The operator receives a distinct `catalog_integrity_failed` signal and can
alert on it without alerting on every unhandled error.

A corrupted record now returns `500` where it previously returned `404`. A
client that treated `404` as "the object is absent" sees a failure instead of
an empty result. That is the purpose: the previous response was wrong.

Recovery of already corrupted records remains a separate task. A migration
that recalculates `passport_digest` fixes only a digest mismatch: a record with
a structurally incomplete passport obtains a matching digest but continues to
be rejected on the revision seal, public visibility, or identity.

An inventory exists: `reconcile_catalog_integrity` scans every publicly
reachable version and returns the versions rejected by the projection together
with each reason and identity. It calls the same `verify_passport_integrity` as
the read path, so it cannot diverge from the behavior it describes, and it
writes nothing: counting does not change object state.

There is still no quarantine state, deliberately. Moving a record into such a
state changes what the catalog reveals about it, which is a contract-level
decision with its own ADR, not a side effect of counting. Until then, a
corrupted record returns the new code and leaves an event.

Tests: conversion of `ValidationError` to `CatalogIntegrityError`; each of the
four readers raises `CatalogCorrupt`; `CatalogCorrupt` is not a
`CatalogNotFound`; the `error`-level event contains the reason and identifiers;
the client does not retry the code on `500`; the code registry remains closed
and complete.

## Reconsideration conditions

Reconsider this decision if the catalog gains a quarantine state—then the
response may become `409` with an explicit state instead of `500`; if search
gains corruption-tolerant delivery—then its behavior must be reconciled with
this decision; or if artifact integrity verification starts failing after the
response stream has begun. Currently every byte-route check runs before the
first byte is sent, so the server still controls the status. An error found
mid-stream cannot change the status and will terminate the connection; that is
a separate decision.
