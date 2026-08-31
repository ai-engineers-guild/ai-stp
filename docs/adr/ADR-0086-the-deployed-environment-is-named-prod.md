---
description: "Decision to name the sole deployed environment prod and resolve the renaming boundary left by ADR-0084."
last_verified: "2026-08-15"
---

# ADR-0086: The sole environment is named `prod`

Status: accepted. Supplements `ADR-0084` without superseding it: the decision
not to have a pre-production tier belongs to that record and is not reconsidered.

## Context

`ADR-0084` removed the staging tier and deliberately left one matter open: its
name. It stated that while `verify_public.py` checks `--expected-environment`
and `.env.prod` declares the value, renaming affects the running service and is
performed as a separate operation, not as a document edit.

The owner decided that there is and will be no separate environment; development
goes directly to production. The name `staging` therefore no longer denotes
anything, and the separate operation is real work.

The scope check found less work than `ADR-0084` anticipated:

- `environment` in the frozen `/v1` contract is a **free-form string**
  (`ai_stp_contracts.auth`, `Annotated[str, Field(min_length=1, max_length=32)]`),
  not an enumeration. The value `staging` appears there only as an **example**:
  in `fixtures/v1/health.json` and the generated `schemas/v1/openapi.json`;
- on the host, `.env.prod.example` already declares
  `AI_STP_API_ENVIRONMENT=prod`.

Thus the contract does not change, and the environment variable already carries
the required value.

The tree nevertheless retained a contradiction that would make deployment fail
if verification ran: `deploy/verify_public.py` declares
`--expected-environment` with the default `staging`, while `.env.prod.example`
sets `prod`. Verification would reject the very host just deployed to.

## Decision

The sole deployed environment is named `prod` everywhere the name affects
behavior or interpretation:

- the default in `deploy/verify_public.py` becomes `prod`;
- the GitHub environment is renamed or deleted together with the already-removed
  deployment job;
- examples and defaults stop naming a nonexistent tier;
- the `environment` example in the contract fixture becomes `prod`, and the
  generated schema is regenerated from the source.

What is **not** done:

- accepted records are not rewritten. `ADR-0044`, `ADR-0046`, and the others
  retain their text: a superseded decision remains readable and points to its
  replacement. This is the ownership rule from `AGENTS.md`, and clean `grep`
  output does not override it;
- the word `staging` is not removed where it means a **temporary directory**,
  not an environment. There are five such places: atomic unpacking in
  `apps/cli/.../toolchain/install.py`, the `backup_staging_pending` state in the
  provider protocol, the temporary candidate-build directory in
  `release_scripts/build_candidate.py`, and tests for those paths. A bulk word
  replacement would break working code; this is the sole reason the edit is
  targeted rather than a tree-wide `sed`.

## Consequences

The environment name ceases to be a historical detail that must be explained to
every subsequent reader. In return, the trace is lost: someone who finds
`staging` in an old commit or accepted ADR will not see it in the current tree
and will arrive here, which is why this record exists.

The divergence between `verify_public.py` and `.env.prod` is removed. It did not
surface only because the deployment job was never assigned; after the job was
removed (`ADR-0084`, implemented 2026-08-15), deployment runs through
`deploy/run.sh` and verification is invoked manually, so a person rather than CI
would encounter the divergence.

`SPEC-024` retains its requirements: most concern topology, TLS, logs, backups,
and SSH identity, all of which remain valid for one environment. The filename
and references to the tier change, not the substance.
