---
description: "Exact target assessment identity, conservative projection, and concurrent ingestion contract."
last_verified: "2026-09-07"
---

# Target assessments

`SPEC-064` owns acceptance requirements and `ADR-0163` owns the assurance boundary.
The generated `TargetAssessmentIdentity` and `TargetAssessmentIngestRequest`
models own wire fields and limits.

An assessment key includes the exact component version and passport digest,
adaptation and harness, scope and projection digest, provider and surface profile,
target scope, harness version, operating system, architecture, and policy version.
Latest pointers retain the complete key. Read projection revalidates the original
passport seal and digest, the pointer key, and every target binding; another
context cannot substitute for missing evidence.

The detail row aggregates all declared exact harness versions, operating systems,
and architectures for one adaptation scope. An empty harness-version declaration
uses the explicit `unspecified` context. Empty OS or architecture declarations do
not narrow the supported contract enums. Every required combination needs current
evidence. Missing or unverified combinations yield `not_verified`; a failure
prevails over other states; otherwise expired or replaced evidence yields `stale`.
A byte-only publication scan records `unspecified` as the observed harness
version. It cannot copy a supported-version declaration into execution evidence;
a version-specific target remains `not_verified` until matching evidence exists.
Only a complete current matrix yields `verified`. A newer current policy or
profile supersedes obsolete evidence for the same context without deleting it.

Concurrent retries serialize on the idempotency key before the replay check.
Identical requests produce one record and one effective result; changing a payload
under the same key is a conflict. The latest pointer advances by observation time.
Equal times retain the more restrictive state in this order: `failed`,
`not_verified`, `stale`, `verified`. A response distinguishes the submitted stored
state from the current effective state, including when replaying an older event.

Future observation times, expiry at or before observation, mismatched observation
artifact/policy/platform identities, and failed checks under a verified verdict
are rejected before evidence writes.

Public evidence references contain validated digests and the current owned policy
identity. Arbitrary writer-provided strings, private links, URL query credentials,
and raw scanner fields are excluded. Check summaries use known bounded fields and
retain the most restrictive result when required contexts disagree.

The publication worker checks each scope with the canonical native projection
verifier. A valid byte scan cannot authorize undeclared, mismatched, or
noncanonical members. Projection integrity failure changes that scope's result
and check summary while leaving shared byte observations intact.

The common-source scan owns the publish gate. The validation snapshot and plan
badge additionally require the complete target matrix. Public reads require
unexpired mandatory bindings from the latest published snapshot for the exact
passport. Reindexing cannot promote expired common evidence. The derived search
column `component_verified_expires_at` retains the earliest mandatory common or
required target expiry; SQL applies it before filters, counts, and pagination.
Migration `0053_component_assurance_expiry` clears legacy component badges in the
search projection until the ordinary index rebuild recomputes their proof.
