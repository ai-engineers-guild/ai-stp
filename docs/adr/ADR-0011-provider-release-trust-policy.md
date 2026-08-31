---
description: "Decision to establish a versioned trust policy for provider releases."
last_verified: "2026-08-03"
---

# ADR-0011: Provider release trust policy

Status: accepted.
Extended by `ADR-0121`: provider release trust has four levels instead of a binary value.

## Context

Providers are distributed separately from `ai_stp` and gain authority to modify a harness's executable environment and target directory. A hash confirms integrity only relative to a manifest that has already been obtained. An arbitrary signature also does not prove an authorized publisher without an established policy.

## Options

1. Verify only SHA-256. Manifest substitution remains indistinguishable.
2. Trust the key specified in the manifest. An untrusted artifact assigns trust to itself.
3. Pin one permanent key without a rotation procedure. Simple verification creates a fragile point of compromise.
4. Use a versioned policy that defines the authorized key or publisher, source, release context, rotation, revocation, and rollback protection in advance.

## Decision

The fourth option is used. Every release is verified against a locally pinned trust policy. The policy defines an authorized key or verifiable publisher, repository, release process, signature subject, allowed schema versions, and minimum sequence.

The client accepts a key-based or keyless signature only when the verifier confirms every policy constraint. A manifest cannot expand the trusted list. An older sequence is blocked except for a separately confirmed rollback to a previously installed verified version.

## Consequences

- a versioned policy and release-manifest contract is required;
- key rotation uses an overlap period;
- revocation blocks new installations but does not automatically delete targets;
- compromise requires publication of a new policy and a list of affected releases;
- `ai_stp`, public providers, and the closed verification circuit use the same reference vectors;
- offline mode accepts only a previously verified cache.

## Reconsideration conditions

The decision is reconsidered if the release system changes, a hardware root of trust appears, the distribution model changes, or safe rotation and revocation of the chosen mechanism proves impossible.
