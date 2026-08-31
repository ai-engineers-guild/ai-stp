---
description: "Machine contract for the profile, plan, and result of local evaluation of an exact SetupVersion."
last_verified: "2026-08-13"
---

# Exact setup evaluation

The requirements owner is
[SPEC-040](../../specs/active/SPEC-040-setup-evaluation-profiles.md). This
document defines the machine boundary of the `eval` commands and the meaning of
their result.

## Objects

`SetupEvalProfile` version `setup-eval/1` describes evaluation intent
independently of a specific setup. It contains scope, a set of component types,
preconditions, checks, assertions, tolerances, budgets, isolation requirements,
and `eval_permissions`. Evaluation permissions are not inherited from the
provider.

`SetupEvalPlan` binds the profile to one exact `SetupVersion`: setup and
component versions, passport/artifact digests, harness/provider/runner versions,
and timestamp. `plan_digest` is computed from canonical content. In subset-eval,
each component MUST belong to the named setup graph.

`SetupEvalResult` contains the full plan, check results, the exact runner,
`result_digest`, and timestamp. `immutable_published_bytes_changed=false` and
`provider_permissions_used=false` are part of the strict result, not a
descriptive promise.

## Commands

- `eval profile [--type <type>]` — display a reference profile without writing;
- `eval plan --setup-id ... --setup-version ... --harness-version ... --provider-version ... --runner-version ...` — persist a content-addressed plan; repeatable `--component-id` limits the scope;
- `eval run --plan-id ... --expected-plan-digest ... --confirm` — execute the available local deterministic subset;
- `eval status --run-id ...` and `eval show --run-id ...` — read immutable evidence without re-execution.

## Honest absence of a runner

Core does not call models and does not present human review as an automated
check. The reference profile declares these checks so that future evidence
coordinates remain stable, but the local runner responds with `not_run`.
Therefore, such a result is `degraded`, not `passed`. `failed` takes precedence
over `degraded`.

The current `local_static` checks exact passport/artifact coordinates and the
type-specific declared native surface. It does not execute the artifact and is
not evidence of functional correctness, security, or trust line.
