---
description: "Decision that an estate complete verdict requires the seven-harness launch matrix; omitted or skipped cells cannot stand in for a passing row."
last_verified: "2026-09-05"
---

# ADR-0160: Estate complete requires a harness launch matrix

Status: accepted.

Clarifies `docs/contracts/estate-release.md` and `ADR-0120` without retagging
a historical consumer or provider release.

## Context

`ai-stp-estate-release/1` already bound a consumer cut to exact provider
identities and six OS×arch legs. `computed_verdict` treated a passing
`software` slice on those six legs as `complete`. Evidence rows had no
provider identity, so one harness filling `(launch, linux, x86_64)` counted
for every harness. Skipping or omitting Antigravity because launch is
undeclared could therefore disappear from the matrix. `known_limitations`
was a free-form string list with no effect, which is correct, but nothing
forced the missing cell to exist.

A21 recorded that Cursor launch is declared via a process-home overlay and
that Antigravity launch stays undeclared because `config_home_env` is empty.
Inventing `ANTIGRAVITY_*` home variables is refused. The remaining honesty
rule from that finding: keep a failing qualification row; do not mark the
estate complete because the operation was omitted from capability
declarations.

## Options

1. Keep consumer-only `complete`. A wheel matrix can still be called a
   system qualification.
2. Encode harness names inside slice strings (`launch:antigravity`) without
   a provider field. Completeness then depends on whoever listed those
   slices, and a record can still omit the name.
3. Require the attested seven repositories, add `provider` on evidence
   rows, and make `launch` a 7×6 matrix. Omit or skip → `incomplete`.
   Fail → `failed`. Limitations explain a cell and never fill one.

## Decision

Option 3. `complete` requires `software` and `launch` in `required_slices`,
exactly the seven attested OpenNetwork repositories, six consumer legs, and
42 launch cells keyed by `(provider, os, arch)`. Schema identity stays
`ai-stp-estate-release/1`: the field is optional on older incomplete
records; a stored `complete` without the matrix is now a lying verdict.

This decision does not publish 0.1.0, does not retag 0.0.65 or 0.1.0, and
does not treat executing Cursor or Antigravity binaries as done.

## Consequences

- `EstateEvidenceRow.provider` is the attested repository identity.
- `REQUIRED_PROVIDERS` in the contract matches `provider-policy.toml`
  `build_attestations`.
- An honest Antigravity undeclared-launch record is `failed` or
  `incomplete`, never `complete`.

## Revisit conditions

Revisit when Antigravity gains a vendor config-home variable that isolates
process home without inventing an environment name, or when a later schema
needs a second provider-scoped slice besides `launch`.
