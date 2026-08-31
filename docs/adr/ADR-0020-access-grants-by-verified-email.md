---
description: "Decision to grant access by verified email through a separate invitation."
last_verified: "2026-08-04"
---

# ADR-0020: Access by verified email through an invitation

Status: accepted.

## Context

The access model recognized only an `AccessGrant` issued to an account identifier. This prevented an identifier from becoming an authority, but blocked a common scenario: an owner wants to share a private object with a person who does not yet have an account or whose identifier the owner does not know.

Without a normative description, an implementation will inevitably invent its own approach, and each obvious option is unsafe. Granting a right directly to an email string turns knowledge of the address into authority. A response saying "no such user" reveals who is registered. Binding access to an unverified address gives it to whoever claims the address first. Retrying without an idempotency key creates multiple rights for one address.

## Options

1. Keep grants limited to account identifiers. Safe, but does not cover the scenario and forces users to exchange identifiers outside the product.
2. Grant a right directly to an email address. Simple, but turns knowledge of the address into authority and has no confirmation point.
3. Introduce a separate invitation state that becomes a right only after the address is verified by signing in.

## Decision

Option 3 is accepted.

**`GrantInvitation` is introduced as a separate entity.** The invitation contains the recipient's normalized address, the object, rights, expiration time, author, state, and idempotency key. An invitation is not an access right.

**The response does not reveal whether an account exists.** Creating an invitation returns the same response regardless of whether the address is registered.

**Confirmation is performed by signing in.** A time-limited one-time key is delivered by email. The invitation becomes an `AccessGrant` only when the signed-in account has the same provider-verified address. A matching string without provider verification is insufficient.

**Conversion is atomic and idempotent.** Reusing the key returns the existing right and does not create another one. An expired, revoked, or already used invitation returns a typed error.

**The owner retains control.** The invitation and the resulting right are revoked and expire independently. Revoking the right does not delete bytes already downloaded by the recipient, and this is explicitly communicated to the owner.

**Email is only a delivery mechanism.** The external email service transports the invitation and does not become a source of identity. The invitation key is not written to logs, traces, or metrics.

**One flow for two clients.** The web and CLI invoke one application flow and one API; no second implementation of access rules is created.

## Consequences

- `SPEC-002` gains requirements for invitation, confirmation, atomic conversion, and revocation;
- `SPEC-013` describes invitation states alongside grant states;
- `architecture/domain-model.md` adds `GrantInvitation` to the identity section;
- `docs/product/glossary.md` distinguishes a grant from an invitation;
- negative checks cover an indistinguishable response, a different address, reuse, expiration, and revocation;
- this decision does not introduce payments or paid access.

## Reconsideration conditions

This decision is reconsidered if a requirement appears to share an object through a recipient-free link, or if verification of the address by the sign-in provider proves insufficient evidence of address ownership.
