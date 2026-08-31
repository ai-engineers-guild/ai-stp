---
description: "Decision to remove indefinite global consent to unverified content and introduce exceptions scoped to a publisher and an object's major line."
last_verified: "2026-08-04"
---

# ADR-0029: Session consent and durable scoped exceptions

Status: accepted.

## Context

`ADR-0016` established that consent to the `experimental` trust line is explicit and lasts for a command or session rather than being stored indefinitely in a profile. At the same time, the global CLI config contained `search.include_unverified`, which did exactly the opposite: it enabled all unverified content for every future query without expiration or scope.

The contradiction is substantive, not merely formal. Indefinite consent "to everything" means any future unverified object by any author enters results forever, while a version with expanded authority inherits consent given to entirely different content. Yet users legitimately need a narrow durable decision: "I trust this publisher" or "I knowingly use this line of this object." Asking again on every query trains users to answer without looking.

## Options

1. Retain the global key. Convenient, but contradicts `ADR-0016` and turns a one-time decision into a permanent unscoped rule.
2. Permit session consent only. Clean, but narrow recurring decisions will be asked until responses become automatic and explicit consent loses meaning.
3. Remove the global key, retain the session request flag, and add durable exceptions with exactly two scopes: publisher and the major line of an exact object.

## Decision

Option 3 is accepted.

**There is no indefinite global consent.** The `search.include_unverified` key is removed from CLI config; no field with that meaning appears in config or profile.

**The session flag remains.** An explicit request flag temporarily opens the `experimental` trust line for the command or session, as before.

**Durable exceptions have exactly two scopes:**

```text
publisher      — all objects from a specific publisher
object_major   — major line X of a specific object
```

The user explicitly chooses the scope. A consent record stores the target, scope, decision author, time, source, and fingerprint of the candidate's authority and capabilities.

**Expanded requirements invalidate consent.** A new major line is not covered by the previous record. A new requirement for authority, processes, network, credentials, external endpoints, managed paths, or native surfaces invalidates the previous record for that version and requires a new explicit decision.

**An exception does not increase trust.** Every result remains in the `experimental` trust line with a separate marker; a consent record never creates platform verification or moves an object into `authoritative`. The consent source and authority fingerprint are recorded in the recommendation trace and installation plan.

## Consequences

- the machine boundary for consent records belongs to `docs/contracts/unverified-consent.md`;
- `docs/contracts/cli-config.md` loses the `search.include_unverified` key;
- `SPEC-006` replaces the indefinite-storage requirement and receives requirements for scopes and consent invalidation;
- interaction policy and the canonical skill ask for consent again for a new major line or expanded requirements;
- consent records synchronize as ordinary user entities.

## Reconsideration conditions

This decision will be reconsidered if the two scopes prove systematically insufficient for real scenarios or if consent records begin to serve as a validation bypass; in that case scopes will be narrowed, not expanded.
