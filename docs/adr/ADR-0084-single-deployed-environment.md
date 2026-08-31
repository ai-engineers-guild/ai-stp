---
description: "Decision to remove the separate staging tier: one deployed environment updated directly from dev, without a pre-production gate."
last_verified: "2026-08-14"
---

# ADR-0084: One deployed environment instead of a staging tier

Status: accepted. Supersedes the staging-tier portion of `ADR-0044`; backups
and rollback from that record are retained and strengthened.
Amended by `ADR-0086`: the sole environment is named `prod`.

## Context

`ADR-0044` introduced a web staging tier as an environment where a change is
verified before production, and built routing, backups, rollback, and a
deployment lock around it. `ADR-0046` separated the trust domains of CI and
deployment, naming staging as the deployment target. Seven more records mention
it in passing.

The tier does not exist and is not planned. There is one deployed environment,
it is updated directly, and work happens there. The product is under
development, and a separate pre-production environment does not justify its
cost: it must be maintained, updated, and explained, while its only consumer is
the same developer who will update the primary environment a minute later.

The discrepancy has already cost time. Documents described staging as an active
gate, the acceptance criteria for `#180` and `#182` required verification
"against staging," and tasks were considered blocked by an environment that
does not exist. Their actual blockers are different and server-side: `#300`,
`#302`, `#303`, and `#312`.

The deployed service also identifies itself as `environment: staging`, so the
documentation is not the only source stating something untrue.

## Decision

There is one deployed environment. There is no separate pre-production tier,
and "verified on staging" ceases to be an acceptance criterion anywhere.

What is **retained in full** from `ADR-0044`: a backup before a change, verified
rollback to the previous exact artifact, and prevention of concurrent
deployments. These mechanisms become more, not less, important: previously the
tier before production caught an error; now nothing except these mechanisms
does.

What is **retained in full** from `ADR-0046`: CI and deployment remain separate
trust domains. This property never depended on staging—untrusted code from a PR
must not share a machine with the deployment key regardless of the target's
name.

What is **removed**: the tier itself, its routing, its separate gate, and the
word `staging` as an environment name.

## Consequences

Pre-deployment verification moves to local `just check` and CI rather than a
separate environment. This is a deliberate tradeoff: speed and one environment
instead of a second chance to catch an error. It is acceptable while the
product is under development and must be reconsidered in a new record when the
deployed environment gains external users.

The deployed environment must be called what it is. Because `verify_public.py`
checks `--expected-environment` and `.env.prod` declares the value, renaming it
affects the running service and is performed as a separate operation, not as a
document edit.

`ADR-0081` treated a schema downgrade as inexpensive "on staging, where an error
costs one run." That environment no longer exists, so this reasoning no longer
applies: an explicit schema rollback remains a permitted operation, but the
cost of an error is now always the production cost.
