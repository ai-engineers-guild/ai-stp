---
description: "Decision to bind the provider plan and apply operation to the same exact HarnessBundle bytes."
last_verified: "2026-08-09"
---

# ADR-0050: Exact HarnessBundle Binding to the Provider Plan

Status: accepted.

## Context

`ADR-0049` made HarnessBundle a real canonical ZIP with logical and byte-level
identities, but the installation consumer continued to invoke `apply-bundle` with the
digest of the internal `ai_stp` plan. It did not pass the ZIP, `validate-bundle` and
`plan-bundle` did not participate in installation, and the provider plan was not
stored at all. A user could confirm a description unrelated to the bytes that the
target's sole writer was supposed to receive.

The `ai_stp` plan hash and provider plan hash answer different questions. The first
identifies the user's decision together with the release, target, and expiration.
The second identifies the change program built by the owner of the native target.
Substituting one for the other validates neither.

## Decision

`install plan` compiles the complete `ai-stp-bundle/1`, atomically stores the exact
ZIP bytes under their raw SHA-256, and passes one absolute content-addressed path in
sequence to `validate-bundle` and `plan-bundle`. Both invocations receive the format,
logical `bundle_digest`, raw `artifact_digest`, and size. `plan-bundle` additionally
receives the current target digest.

The consumer accepts responses only when the provider returns the exact same values
for those fields. Validation requires `valid=true`. The provider plan requires
`state=planned`, a canonical `plan_digest`, the same target digest, and a non-empty
effect list.

Immutable plan schema v5 binds:

- `bundle_format`;
- `bundle_digest`;
- `bundle_artifact_digest`;
- `bundle_size`;
- `provider_plan_digest`.

All five fields enter the digest confirmed by the user. The local absolute cache path
does not: it is a derived location of the bytes, may differ on another device, and is
not their identity.

Before `apply-bundle`, the consumer rehashes the cached artifact and validates its
size. The provider receives the same bundle bindings, the original target digest,
and the exact provider plan digest. Its response must repeat all bindings. A mismatch
after invocation is not described as an ordinary failure: an effect may already have
occurred, so the operation becomes `partial`. `resume` neither passes the package nor
repeats apply; it invokes only `provider-info` and `status`.

## Compatibility

The protocol v1 command set does not change, no network fields are added, and the
frozen network semantics remain unchanged. This decision specifies the previously
absent mandatory argv/response contract for the already declared `validate-bundle`,
`plan-bundle`, and `apply-bundle`. A provider that responded to command names but did
not accept HarnessBundle was not an executable implementation of the installation
contract.

Old schema v1–v4 plans retain their historical digest. They can be inspected and
completed through observe-only recovery, but no new effect is applied from them:
missing exact bytes and a provider plan cannot be reconstructed by guessing.

## Consequences

User confirmation, the byte cache, provider validation, its plan, and apply now form
one verifiable chain. Repeating `install plan` may repeat read-only provider calls,
but identical responses produce one idempotency key and the existing operation. The
cost is one local cache artifact and a stricter provider adapter; real Claude Code
and Codex providers must implement this wire contract before E2E.

## Reconsideration Conditions

The decision will be reconsidered if a streaming bundle protocol is introduced in
which the provider does not receive a local path. The new transport form must
preserve both identities, the size, provider plan digest, and `partial` semantics
after invocation.
