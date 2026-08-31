---
description: "Decision to allow a setup to declare zero components, separating managed emptiness from removal from management."
last_verified: "2026-08-26"
---

# ADR-0124: A setup may declare zero components

Status: accepted.

## Context

`SetupVersionPassport.components` carried `Field(min_length=1)`. No normative
document named this restriction: neither `docs/contracts/`, `specs/active/`,
nor an ADR. It had a test—`test_setup_requires_components_and_one_harness`
checked it together with the one-harness rule—but a test preserves behavior; it
does not decide it. Two unrelated rules in one assertion mean neither was
considered separately. The restriction existed in the model and was generated
from it into `schemas/v1/setup-version-passport.schema.json`,
`schemas/v1/catalog-setup-version.schema.json`, and `schemas/v1/openapi.json`—
thus published as a contract without being anyone's decision.

A rule of this kind is discovered only through a collision. That happened:
`select propose` rejects zero participants with its own message, and deeper
behind it the model also rejected them—but with a second refusal unknown to the
first.

Separately, an external experiment series reports that an empty `SetupVersion`
can be installed and rolled back (`#421`, `#426`). This is true and also means
our own model rejects the passport used there—it was created outside the public
path, as the experiment's author states explicitly.

## Options

**Keep the prohibition and close `#426` with a refusal.** Inexpensive and
defensible by one argument: a setup projecting nothing has the same effect as
removal, and a second word for one concept is precisely the trap this repository
already addressed in `ADR-0123`.

The argument is rejected because the effects are not identical—see below.

**Allow zero and record how it differs from removal.** Accepted.

**Allow zero only for private versions.** Rejected: immutability and public
version provenance do not depend on participant count, and a visibility-based
exception would introduce a third rule where one suffices.

## Decision

A setup's composition may be empty. An empty composition is **a composition,
not an absence**.

The distinction that prevents it from being synonymous with removal:

| | target after the operation | what an appearing file means |
|---|---|---|
| empty setup installed | `managed`, declared content is empty | drift |
| installation removed | `unmanaged` | nothing; the target is not monitored |

Managed emptiness is a monitored state. Removal is an unmonitored state. These
are different assertions about the target, each with its own verb: `install`
and `remove` remain what they were.

Public surface: `select propose --empty` (`REQ-630`). Zero participants without
the flag remains a refusal because that is exactly what an unsuccessful search
returns, while an immutable object is being frozen. The flag together with
participants makes a false assertion about the call and is rejected rather
than ignored. Confirmation is not weakened: `--empty` says "the composition is
empty," while `--confirm` says "freeze exactly this," and the former does not
imply the latter.

## Consequences

- `min_length=1` is removed; the three generated schemas lose `minItems: 1`.
  For a consuming validator this is an expansion: everything accepted before
  remains accepted.
- Measured rather than assumed: the full backend run after removal is green,
  and no other composition non-emptiness check was found in the tree
  (`apps/platform`, `apps/api`, `packages`). `evaluation.py` retains its own
  `min_length=1` on another object and is unaffected.
- A previously absent primitive appears: a baseline for rollback evidence.
  Install an empty setup, modify the target, and roll back—a sequence requiring
  no prepared content.
- The cost is explicit: "setup" no longer guarantees at least one component.
  Code reading `components[0]` without checking would already have been wrong—a
  passport could arrive from the network—but is now wrong by contract as well.

## Reconsideration conditions

- If an operation appears for which managed emptiness and removal produce the
  same observable target state, the distinction no longer holds and this record
  must be reconsidered in full.
- If an empty composition proves able to bypass a participant-bound check—
  authority, licenses, or trust line—the rule is incomplete: that check then
  belongs to the setup rather than its participants and requires a separate
  decision.
