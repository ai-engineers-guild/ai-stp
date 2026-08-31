---
description: "Decision to issue a local owner identity before sign-in and transfer passport ownership upon first sign-in."
last_verified: "2026-08-06"
---

# ADR-0060: Local Owner Identity

Status: accepted.

## Context

The passport envelope requires an `owner_id` of the form `account_…` (`passport-envelope.md`). The account is issued by the server: `DeviceTokenResponse` from the frozen `/v1` returns `account_id` in response to a successful sign-in.

At the same time, `offline-capability.md` classifies reading, modifying, and revising the developer passport as offline operations, while `SPEC-001` makes the local environment fully usable without an account. Issue #74 requires creating the developer passport in an environment where sign-in does not yet exist: it will only appear in #75.

Therefore, the passport must be created before the account identifier becomes known. Not creating it before sign-in would mean that the offline environment does not work without a network connection—a direct contradiction of the accepted decision.

## Alternatives

1. Defer passport creation until the first sign-in. This is the simplest option, and it also eliminates offline capability.
2. Make `owner_id` optional. This requires changing the frozen passport envelope for a state that is temporary and leaves the passport without an owner in a model where ownership determines access (`SPEC-003` REQ-301).
3. Use the device identifier as the owner. This is fundamentally incorrect: there is one developer passport across all devices, and it is merged between them (`SPEC-009` REQ-911), whereas a device identifier belongs to a single device.
4. Issue a local owner identifier and transfer ownership upon first sign-in.

## Decision

Alternative 4 is accepted.

When the passport is first created, a local `account_…` is issued—a typed identifier from the same prefix registry. It identifies the owner of this installation and is stored alongside the device identity.

Upon the first successful sign-in, ownership is transferred to the account identifier issued by the server. The transfer is performed as a regular revision: `owner_id` is part of the content, so changing it creates a new revision with the previous revision among its parents. The history is preserved, the moment of ownership transfer is visible in the graph, and nothing is rewritten in place. The responsibility to perform the transfer belongs to #75; after the transfer, the local identifier remains in the history and is not reused.

The local owner identifier is not sent to the server and does not appear in any `/v1` request: it is not an account and must not be represented as one.

## Consequences

- the offline environment creates and modifies passports without a network connection and without an account, as promised;
- the frozen passport envelope remains unchanged;
- #75 gains a mandatory step: transfer ownership upon first sign-in; otherwise, local passports will remain owned by an identifier unknown to the server;
- until sign-in has occurred, `owner_id` in local passports does not match any server account, and this is a normal state, not an inconsistency;
- a second sign-in with a different account on the same device does not silently merge passports: this is a separate case addressed by `SPEC-002` REQ-202.

## Reconsideration Conditions

The decision is to be reconsidered if the server begins accepting an account identifier proposed by the client—in which case ownership transfer will no longer be necessary—or if a scenario emerges in which local passports are created only after sign-in and offline capability before sign-in is no longer required.
