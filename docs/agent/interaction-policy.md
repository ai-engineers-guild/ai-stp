---
description: "Confirmations and questions in the configuration workflow."
last_verified: "2026-08-09"
---

# Interaction Policy

The user's task defines the scope of authority. Local reversible steps that are
part of the requested outcome are performed continuously until a verified state
is reached; there is no need to ask again before each one. A request to prepare,
install, update, or repair a setup already authorizes inspection, planning,
application, verification, and recovery within that setup.

A separate decision is required when something outside the task arises:

- a required passport fact is unknown and the alternatives materially change the result;
- an unresolved conflict cannot be resolved mechanically;
- consent to the `experimental` lane or selection of an object from an unverified author;
- a public version, major version line, visibility change, access rights, or invitations;
- linking credentials or an account, or elevating privileges;
- complete cleanup or deletion of a target or backup with no recovery path;
- an external Git or deployment action not requested by the task.

Checking the digest, preconditions, idempotency, and plan match is always
required and is not a question for the user: it is machine confirmation that
the approved effect is exactly what will be performed. A stale plan is handled
by building a new one and showing the difference; a new decision is required
only if the effect itself changed.

Consent to the `experimental` lane applies within a command or session; no permanent global consent setting exists. A durable exception is created only through an explicit user choice and in exactly two scopes—a publisher or the major line of an exact object, as defined by `docs/contracts/unverified-consent.md`. A new major line and any expansion of capabilities, network access, credentials, external endpoints, managed paths, or native surfaces require a new explicit decision.

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
