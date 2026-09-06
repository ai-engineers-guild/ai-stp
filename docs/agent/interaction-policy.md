---
description: "Confirmations and questions in the configuration workflow."
last_verified: "2026-09-05"
---

# Interaction Policy

The user's task defines the scope of authority. Local reversible steps that are
part of the requested outcome are performed continuously until a verified state
is reached; there is no need to ask again before each one. A request to prepare,
install, update, or repair a setup already authorizes inspection, planning,
application, verification, and recovery within that setup.

A separate decision is required only for the remaining stops in
`skills/canonical/ai-stp/references/decisions.md`:

- visibility or access of an existing object;
- linking **someone else's** account or new third-party credentials;
- elevating system privileges;
- deleting data, a target, or a backup with no recovery path.

Uncertainty is more inspection or a reversible experiment, not a permission
question. Unverified and `experimental` objects may be used under task
authority and stay labeled. Publishing, committing, merging, and deploying
verified work that the task already requested are inside that authority.

Checking the digest, preconditions, idempotency, and plan match is always
required and is not a question for the user: it is machine confirmation that
the approved effect is exactly what will be performed. A stale plan is handled
by building a new one and showing the difference; a new decision is required
only if the effect itself changed.

Consent to the `experimental` lane applies within a command or session; no permanent global consent setting exists. A durable record is created only through an explicit choice in the scopes defined by `docs/contracts/unverified-consent.md`. Under an authorized `task` / `full-auto` profile (`ADR-0150`, `ADR-0159`) a new major line or capability expansion does not require a new publisher or object-major grant; a revoked narrower record remains an exclusion. Without task authority, a new major line and any expansion of capabilities, network access, credentials, external endpoints, managed paths, or native surfaces require a new explicit publisher or object-major decision.

No question is needed for reading, repeatable local validation, or deterministic regeneration without a semantic change.

## Machine-Help Mutability Classes

The Agent reads `mutability` and `confirmation` independently: `confirmation: none` does not turn a mutating command into a read, and a mutability class alone does not authorize a sensitive action.

- `read` only observes: it does not create an identity or local registry, run a migration, or change existing state;
- `plan` stores an exact plan or short-lived session snapshot, but does not create a version or change a target;
- `apply` changes local or external state; the required method for recording the user's decision is defined by the separate `confirmation` field;
- `destructive` deletes data, a target, or a backup and always requires a separate decision under the rules above.

Empty local state for a collection returns an honest empty result when the collection's absence is normal. A command that requires an existing object or context returns a typed refusal with a safe next action and creates nothing itself.

## Post-Installation Authorization

The Agent reads `required_authorization` from the `install plan` result and, before
confirmation, explains the kind of requirement to the user. It does not ask for a
token as an argument, read a secret value, or set a local "ready" marker.

After native configuration, the Agent calls `target status` with the same verified provider.
The `pending_authorization` field is the consumer's canonical decision: a non-empty
value means `needs_configuration`; an empty value means there is no separate pending
authorization. The Agent does not infer readiness from a successful install, the presence
of an environment variable, or the user's words. An old provider without authorization
evidence remains compatible but cannot confirm `ready`; in that case, the Agent reports
the limitation and suggests updating the provider without looping apply.
