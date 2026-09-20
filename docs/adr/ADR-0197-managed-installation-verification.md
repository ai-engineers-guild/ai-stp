---
description: "Read-only verification that a managed target still carries the organization-approved setup and components."
last_verified: "2026-09-20"
---

# ADR-0197: Managed installation verification

Status: accepted. Extends ADR-0194, ADR-0195, and ADR-0196.

## Context

Milestone 6 issue 216 lets CI prove that a project or machine uses exactly
the organization-approved setup and components. The CLI already records every
provider-verified installation, caches the exact HarnessBundle it applied,
and can recompute managed-path digests without touching provider state. What
did not exist was a single verdict that compares those records against the
live target and the current corporate policy - and a false "tampered" verdict
was the stated failure mode, because a later authorized installation on a
shared provider target must not read as local drift.

## Decision

`corporate assignment verify` composes three evidence layers the repository
already owns and adds no fourth writer. The durable verification log names
the newest verified installation for the (project, harness) pair; the cached
bundle manifest supplies the expected setup and component coordinates and the
expected managed-path digests; the provider's read-only `status` observation
supplies the current target digest and shadowed surfaces when available. The
newest provider-verified operation on the provider target - whichever pair
owns it - is the authorized baseline, so an authorized upgrade another pair
performed is `expected_change`, not drift.

Each setup and component line carries its exact coordinates and one
classification: `unchanged`, `locally_modified`, `missing`, `extra`,
`unverifiable`, or `expected_change`; drifted member paths attribute a line
to its component. When the assignment layer answers, the same plan contract
from ADR-0196 evaluates the materialized coordinates, and per-line outcomes
join the evidence. One verdict summarizes the check: `fail` for any proven
local difference, then `revoked`, `unsupported`, `outdated`, or `not_enrolled`
from policy outcomes, then `unverifiable` whenever evidence is missing or the
corporate layer is skipped or unreachable, and `pass` only when both layers
agree. An offline run can never report `pass`.

The result binds the check to organization, account, project, technology, and
harness, and carries coordinates, digests, classifications, and timestamps
only. Verification writes nothing: no repair, no apply, no provider write,
and no upload of repository contents, prompts, secrets, or files.

## Consequences

The CLI gains one read-only command and the contracts gain one generated
result schema (`cli-managed-verification`) consumed by CI; the provider
remains the only writer of active harness state. `managed_diff` gains a
bounded reader for bundle setup/component bindings, and the local target log
gains a query that finds the newest verified operation on a provider target
across pairs. Tests cover clean and drifted targets, missing and extra
managed content, later authorized installations, every policy verdict,
offline and unreachable corporate layers, and the absent-content guarantees.
Rollback removes the command and schema while retaining installation and
verification history.
