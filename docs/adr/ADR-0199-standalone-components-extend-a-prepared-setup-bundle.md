---
description: "Standalone exact components extend one prepared setup bundle without changing the verified baseline."
last_verified: "2026-09-20"
---

# ADR-0199: Standalone components extend a prepared setup bundle

Status: accepted. Implements the local half of ADR-0197; leaves the verified
baseline rule of ADR-0050 intact by extending what a bundle may carry.

## Context

ADR-0197 plans one installable unit per assignment line, and ADR-0198 verifies
the materialized target against every effective assignment. An employee whose
assignments are one setup plus several standalone components could install the
setup, but the standalone lines had no `install plan` form: a proposal freezes
its members at confirmation, so assigned components cannot be appended to it,
and a component-only install would leave the baseline unset.

## Options

1. Repeatable `--component <stable_id>@<X.Y>` on `install plan --setup`:
   the named prepared SetupVersion stays the baseline and each standalone
   component joins the bundle as an extra graph root.
2. A component-only installation mode: the bundle carries only components and
   no setup records a baseline.
3. A synthetic composed setup per employee: the corporate side would mint one
   setup object per distinct member set.

## Decision

Option 1. `install plan` accepts repeatable `--component <stable_id>@<X.Y>`
only together with `--setup` on the `install` action. Each component must be
an exact component passport already held by this registry; a missing one
refuses with `AI_STP_NOT_FOUND`, a non-component one with `AI_STP_CONFLICT`,
and a duplicate or a member-restated-at-another-version with
`AI_STP_VALIDATION_ERROR`. Components join the bundle as additional
`graph.resolve` roots — identical restatements collapse, conflicting
coordinates are the same `version_conflict` refusal setup members live under.

The recorded installation baseline remains the named SetupVersion: status,
idempotency, and `corporate assignment verify` keep comparing against it,
while the bundle manifest lists every setup member and standalone component
the materialization wrote, so verification sees assigned components it
installed. A proposal still cannot gain members after confirmation, and
sourceless actions (`backup`, `rollback`) reject the option outright.

## Consequences

`install plan --setup <id>@<X.Y> --component <id>@<X.Y>` is the complete
remediation `corporate assignment verify` names for an assigned setup plus
assigned components. The `install` task intent still installs the setup alone;
standalone members are a direct-command surface, not an interactive-question
change. The option is v3-only in practice — it extends the exact bundle that
protocol v3 validates — and protocol v1 flows never receive it.

## Revisit conditions

Revisit if the corporate side mints per-employee composed setups (option 3
becomes free), if verification must prove component provenance beyond the
manifest digest list, or if a future protocol requires components to record
their own baseline identity.
