---
description: "Decision that authorized full-task authority is consent scope task, not a config wildcard and not a covering grant that beats a narrower exclusion."
last_verified: "2026-09-05"
---

# ADR-0159: Full-task authority is consent scope `task`

Status: accepted.

Supersedes the “exactly two scopes” clause of `ADR-0029` and the part of
`ADR-0029` that required a new explicit publisher or object-major decision
for every capability expansion. Does not restore `search.include_unverified`.
Does not rewrite `ADR-0150`; this record is the machine model that decision
asked for.

## Context

`ADR-0029` removed indefinite global consent and closed durable exceptions at
`publisher` and `object_major`, with fingerprint invalidation. `ADR-0150`
then authorized the agent, under a full-task / full-auto profile, to use an
unverified object without a fresh human grant per object or capability
expansion, while keeping the object labeled unverified.

`consent.consulted` implemented only the two fingerprint scopes. There was
no first-class task authority. A narrower refusal could still be coded as
“any covering grant wins” (the A06 bug). Empty `observed` refused every
task-shaped record. The contract and the policy disagreed.

## Options

1. Keep two scopes and treat full-auto as documentation. Agents keep
   re-prompting or inventing a wildcard.
2. Reintroduce a config key that allows every unverified object. Restores
   the thing `ADR-0029` removed.
3. Add scope `task` with target `full-auto`. Named, revocable, beaten by a
   narrower exclusion, never a trust-lane promotion.

## Decision

Option 3. The closed list is:

```text
publisher
object_major
task
```

`task` accepts only target `full-auto`. Any other target is refused. A
revoked `object_major` or `publisher` record is an exclusion and answers
first. An active fingerprint record that still covers is the source when it
applies. An active `task` grant covers without a fingerprint or major
ceiling. Consent does not move a candidate to `authoritative`.

## Consequences

- `docs/contracts/unverified-consent.md` and `SPEC-006` name three scopes.
- `ConsentRecord.scope` on the wire includes `task`.
- `consent allow --scope task --target full-auto` does not require a
  registered object: the authority is the profile, not a candidate shape.
- Interaction policy no longer demands a new publisher/object-major grant
  for capability growth when task authority is in force.

## Revisit conditions

Revisit if a second authorized profile is required, or if a `task` grant is
observed promoting an object to `authoritative`.
