---
description: "Decision to separate persistent CI and deployment runners, pin the SSH identity, and verify the public staging route."
last_verified: "2026-08-29"
---

# ADR-0046: Separate CI and Staging Deployment Trust Domains

Status: accepted; the separation of trust domains remains fully applicable and
never depended on the staging tier—the deployment target was renamed in `ADR-0084`.
The CI role mechanism was revised after the move to fully ephemeral checks;
that record belongs to private infrastructure and is not published here.
The separation of trust domains and the entire deployment portion remain unchanged.

What applies in this tree: checks run on GitHub-hosted runners, not persistent
self-hosted ones. The runner class below is described as context for the original
choice.

## Context

Pull-request checks and automated staging deployment ran on the same class of
persistent self-hosted runners. Code from a pull request could leave a file, process,
or environment modification on the machine, and the next push to `dev` on that same
machine would gain the SSH key and network access to staging. Restricting
`GITHUB_TOKEN` does not eliminate state that survives a job.

The same workflow canceled the previous run on a new push even though the deployment
job had separate serialization. The SSH host identity was accepted from the current
`ssh-keyscan` response, while the post-deploy probe ran on the server itself through
loopback with TLS validation disabled. This combination proved internal container
readiness, but not the user-facing DNS/TLS route or the exact deployed SHA.

## Decision

- CI uses only runners with the `guild-ai-stp-ci` role; deployment uses only
  `guild-ai-stp-deploy`. No single runner, user, filesystem, or host carries both
  roles. The CI domain receives no deployment secrets and has no SSH route to staging.
- Deployment secrets belong to the GitHub `staging` environment. Before using
  secrets, the job verifies that its runner differs from both check runners, that the
  SHA is exactly one merge commit of an allowed pull request into `dev`, and that the
  actor and source personal branch are in explicit allowlists.
- Cancellation remains enabled only for pull requests. A push run is not canceled by
  a new push; deployment jobs are additionally serialized by a shared concurrency
  group and host-side `flock`.
- SSH trusts only the pre-pinned `known_hosts` content from the environment. A network
  response does not create a root of trust. Key rotation uses an explicit overlap
  period for the old and new keys.
- Before the tree is transferred to the server, a durable marker for the exact SHA is
  written. Every host-side stage atomically updates the marker; after interruption,
  the next run deterministically repeats the idempotent forward path. The current and
  previous artifacts change only after successful readiness.
- The internal host check remains. After it, the deployment runner accesses the
  ordinary public HTTPS origin: without DNS substitution or disabled TLS, it checks
  public liveness, readiness, and web responses, as well as the commit, environment,
  and single schema-head revision values.

The self-hosted model remains: GitHub-hosted minutes are not required for these jobs.

## Consequences

Physically separate runners and the GitHub `staging` environment must exist before
the workflow is enabled. Changing only the label is insufficient; configuration is
proven by a negative shared-machine check and a documented owner inventory. If a
required variable, pinned key, PR association, or external probe is unavailable,
deployment fails closed.

Deployment receives read-only access to pull requests through the GitHub API. Public
diagnostics already belong to `SPEC-024` and are not expanded with secret fields.
`.backups`, `.deploy-state`, and host-only environment files are excluded from tree
synchronization and are not deleted by `rsync --delete`.

Rollout order: create separate runner users/hosts and labels; create the environment
and move secrets/variables into it; run a negative isolation probe; only then enable
the changed workflow. Until then, the patch is not ready to merge.

## Reconsideration Conditions

The decision will be reconsidered upon a move to fully ephemeral CI, a separate
deployment controller, or an orchestrator that issues a short-lived identity instead
of an SSH key.

Both parts of this condition occurred, the second later than recorded here.

Checks moved from persistent self-hosted machines to ephemeral ones, and then to
GitHub-hosted runners; the runner-class decision belongs to private infrastructure
and is not published here.

Deployment stopped holding a long-lived SSH key: under `ADR-0103`, the target pulls
a monotonic ref itself, while CI receives no key and does not log in to the server.
Verified in `.github/workflows/deploy.yml`: there is no `ssh`, `scp`, `known_hosts`,
or private key; the workflow advances the ref and confirms that the host caught up.
The previous statement that it "still holds a long-lived SSH key" was true when
written and later ceased to be true without being rewritten.
