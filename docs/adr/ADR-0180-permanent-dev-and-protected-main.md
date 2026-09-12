---
description: "Permanent dev integration and protected main promotion with administrator bypass."
last_verified: "2026-09-12"
---

# ADR-0180: Permanent dev and protected main

Status: accepted. Supersedes the branch-policy portion of ADR-0115.

## Context

The owner requests two permanent branches, default `dev`, work-branch PRs into
`dev`, and promotion PRs from `dev` into protected `main`. The previous single-line
documentation and unprotected GitHub configuration contradict that request.

## Decision

Keep `main` and `dev` locally and remotely. Create `dev` at the exact current
remote `main` SHA, without rewriting identifiers or history. Use merge commits
for work integration and promotion. Check pushes to both permanent branches and
all PRs; deployment remains limited to successful exact-SHA `main` checks.

GitHub rulesets block ordinary deletion and force updates of permanent branches,
require PRs with zero required approvals, and require `branch-policy` for main
promotion. The check accepts only same-repository `dev` into `main`; other PR
targets retain the existing conventional work-branch naming rule. A separate
main update restriction permits repository administrators only. Administrators
can explicitly bypass promotion and check rules for exceptional operations.
This applies to every current administrator, not exclusively one account; no
collaborator is demoted by this change.

Disable automatic branch deletion so promotion cannot delete permanent `dev`.
Delete finished work branches explicitly. Local integration rehearsals do not
replace remote PR evidence. Synchronize promotion merge commits back into `dev`
through a PR, preserving ancestry before the next development cycle.

## Consequences

No multiple approvals or second human reviewer blocks the owner. Administrator
bypass remains powerful and must be named in operational reports. The required
source check is not a new staging environment or an alternative product gate.
Final-SHA CI and local validation remain required by the working task.

Rollout creates `dev`, changes the default, publishes the branch-policy workflow,
then enables rulesets and reads their live configuration back. Unknown/unpublished
status checks must not be mistaken for green checks. Rollback changes the default
back to `main`, disables only these rulesets, and reverts the configuration commit;
retain `dev` and all history. Never delete integration data as rollback.

## Revisit conditions

Review bypass actors when administrator membership changes, and required check
names when workflow jobs change. Reconsider approval policy only by owner decision.
