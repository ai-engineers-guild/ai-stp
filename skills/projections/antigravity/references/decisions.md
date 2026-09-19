# Decisions

The user's task is the authority boundary. Local reversible steps inside that
task run without a fresh question (`ADR-0150`).

`mutability` and `confirmation` are independent.

`confirmation: none` is not consent. `plan_digest` is a machine binding of exact
bytes, not a person.

- `read` — observe.
- `plan` — exact subject of a later apply.
- `apply` — when the current request already authorizes it.
- `destructive` — only when there is no recovery path.

A separate user decision is required when: visibility or access of an existing
object changes; **someone else's** account or new third-party credentials are
linked; system privileges are elevated; or data, a target, or a backup is
deleted without recovery.

An unresolved engineering choice, an unverified or experimental object, Git
promotion, and deploy of verified work are not that list. Unverified stays
labeled unverified. Experimental may enter composition under task authority
and never becomes `authoritative` by that fact.

For `explicit_flag` on remaining expert stops, obtain the decision, then pass
the parameter named by the descriptor. `plan_digest` is bound in-process by
shipped task intents; do not type `install plan` to obtain a digest for
`install`, `change`, or `switch`. Expert families that still declare
`confirmation: plan_digest` take the digest from that family's plan command
named by machine help. Do not compute it. A stale plan is replanned
automatically.

Digest, precondition, and idempotency checks are mechanical, not questions.
Uncertainty triggers more inspection or a reversible experiment.
