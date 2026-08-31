---
description: "Decision to introduce three trust lanes and explicit consent for unverified objects."
last_verified: "2026-08-04"
---

# ADR-0016: Trust lanes and explicit consent for unverified objects

Status: accepted.

## Context

The previous rule stated that objects from unverified authors were shown in a separate experimental block only when there were not enough verified alternatives. This described result presentation, not a trust policy.

The wording led to two incorrect conclusions. First, an unverified object appeared as an implicit fallback: whether it was shown depended on verified candidates running out, not on the user's decision. Second, the user's own local or imported object had no place in the model at all: it is not a publication by a verified author, but the user owns it and must be able to select it directly, including offline.

No document defined where consent for unverified content was stored, how long it remained valid, or what prevented an agent from carrying an unverified reference into an automatic composition through free-form text.

## Options

1. Retain the fallback block when verified candidates are insufficient. This requires no changes but leaves implicit trust elevation and does not describe owned objects.
2. Completely prohibit unverified objects in the MVP. This is safe but makes it impossible to work with owned and imported objects or with a cold catalog.
3. Introduce three explicit trust lanes with separate inclusion rules for results.

## Decision

Option 3 is accepted.

**Three lanes are defined.**

```text
authoritative
  verified author
  complete passport
  required checks are current
  evidence of compatibility with the target

experimental
  unverified third-party author
  included in results only with explicit consent
  separate response section, separate label

local_owner_or_pinned
  owned, imported, or exactly pinned object
  local checks have passed
  selected directly, including offline
```

**Consent is explicit and limited.** Unverified objects are included in results only when the request has an explicit flag such as `include_unverified`. By default, consent applies within a single command or session and is not stored indefinitely in the profile.

**Silent elevation is prohibited.** An object from `experimental` is not moved into `authoritative`, either automatically or by an agent's decision. The absence of verified candidates is a normal state and does not enable the fallback lane by itself.

**An owned object does not become platform-verified.** The `local_owner_or_pinned` lane permits installation after local checks, but does not grant platform-verification status and is not displayed as a verified object.

**The decision trace records the lane.** A recommendation record stores each candidate's lane, author state, consent source, required-check results, and compatibility evidence.

**The two verification axes are distinct.** `author_verified` applies to an author or namespace, while `component_verified` applies to a specific object version. A verified author does not make a version verified, and vice versa. The `authoritative` lane requires both axes; search filters support them separately.

## Consequences

- `SPEC-006` replaces the fallback-block requirement with requirements for lanes, consent, and prohibition of elevation;
- `SPEC-007` and the object card display both verification axes separately;
- `AGENTS.md`, the canonical skill, and the interaction policy describe consent as a separate user decision;
- search gains filters by lane, `author_verified`, and `component_verified`;
- negative checks prove that an agent cannot return an unverified reference in an automatic composition.

## Reconsideration conditions

The decision shall be reconsidered if a verifiable mechanism emerges that gives a third-party object `authoritative`-level evidence without author verification, or if separate consent proves behaviorally indistinguishable from verification to users.
