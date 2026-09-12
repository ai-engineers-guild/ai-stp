---
description: "Rules for branches, commits, pull requests, and cross-repository changes."
last_verified: "2026-09-12"
---

# Git workflow

## Branches

`dev` is the repository's default integration branch. `main` is the protected release branch. Both are permanent locally and on GitHub. CI push branches: `dev`, `main`.

Contributor branches use exactly one of these prefixes followed by a non-empty
description: `feat/`, `chore/`, `docs/`, `test/`, `fix/`, or `refactor/`.
Branches with other prefixes—including `claude/` and `codex/`—are rejected by
the CI contract check. `main` and `dev` are exempt from this naming rule.

ADR-0180 restores the two-branch workflow at the owner's request and supersedes the branch-policy portion of ADR-0115. No mandatory human approval is required.

Contributors work in personal branches that follow this prefix rule.

Create each work branch from current `dev`; keep it current by merging `dev`. Publish the work branch and open a PR into GitHub `dev`. After green CI on the exact final HEAD, merge it into `dev` with a merge commit. Then open a promotion PR from same-repository `dev` into `main`, verify its exact HEAD and merge. Ordinary PRs into `main` from any other branch fail the required `branch-policy` check. Only repository administrators can update `main`; they have an explicit bypass for exceptional merges from other branches without approvals. Bypass is not evidence that checks passed.

When CI is unavailable, evidence is a complete `just check` run on the exact
HEAD. Its output—commands run, test count, and coverage—is recorded in the merge
commit message. This substitutes the evidence, not the requirement: merging
without any run is never allowed. This rule is written here because the runner
has already been unavailable and merges proceeded this way; a silent mismatch
between practice and the rule is worse than either explicit option.

The project owner may merge another contributor's pull request when the author
would otherwise remain blocked. In that case, the person merging resolves the
conflicts.

Automatic branch deletion is disabled to preserve `dev` after promotion. Delete completed work branches explicitly; never delete `main` or `dev`. Both permanent branches reject force pushes and deletion for ordinary contributors.

```text
dev → work branch → PR into dev → green CI → merge into dev
dev → promotion PR into main → green CI → administrator merge
fetch → fast-forward local main → synchronize local dev → next work branch
```

GitHub `dev` is the integration source of truth; `main` is the release source of truth. Local rehearsal merges do not replace GitHub PRs: publish a work branch and PR it into `dev`, rather than pushing a locally merged `dev` directly. After promotion, fetch, fast-forward local `main` to `ai-stp/main`, and synchronize local `dev` with `ai-stp/dev`. If `main` has a promotion merge commit absent from `dev`, return it through a synchronization PR into `dev`; never force-reset shared history. Local divergent commits are preserved and reconciled explicitly.

For a clean checkout after the synchronization PR lands:

```powershell
git fetch ai-stp
git switch main
git merge --ff-only ai-stp/main
git switch dev
git merge --ff-only ai-stp/dev
git switch -c feat/next-change
```

Git has no native local protected-branch setting; local agents obey this workflow
and GitHub enforces remote writes. The applied ruleset sources are
`.github/permanent-branches.ruleset.json`, `.github/main-promotion.ruleset.json`,
and `.github/main-admin-updates.ruleset.json`. Read live rulesets and repository
settings back after updates; source files alone do not prove enforcement.
Administrators bypass every rule in these rulesets, including deletion and force
push prevention; permanent-branch preservation remains mandatory operating policy.

The repository has several contributors. This does not contradict the single-user product model in `docs/product/vision.md`: that document describes whom the product serves, while this one describes who writes it.

A significant change starts with a draft PR from a work branch to `dev`. GitHub rulesets enforce permanent-branch preservation, PR integration, and the `main` promotion boundary; see `quality-gates.md`.

The history-rewrite prohibition applies to `main` and `dev`. A work branch belongs to its owner; nobody rewrites another contributor's branch.

### `.gds/compiled-policy.json` is not a rule of this repository

The file is a projection from an external control plane, not the source of truth for contributors. It marks some GitHub settings as `managed`, but nothing here applies them or checks drift, and observed repository values differ from the declarations—notably in the allowed merge methods.

This document defines the merge method. The projection does not override it. Until something actually writes settings from the projection and checks drift, it remains a reference snapshot and cannot be cited as an active rule.

## Commits

Allowed types:

- `docs`;
- `feat`;
- `fix`;
- `refactor`;
- `test`;
- `chore`;
- `perf`.

A commit is atomic for one reason. Generated output and its source change together, except for a separately verified version or artifact promotion commit.

Only explicitly listed paths are staged. A blanket command that stages the entire working tree is prohibited: agent tools write to nested service directories during a session, and unrestricted staging collects unrelated files into the commit.

## Pull request

The pull request description contains:

- purpose and scope;
- affected specifications, ADRs, schemas, and public contracts;
- exact base and head SHAs;
- migration, compatibility, and merge order;
- commands run and observed results;
- checks that were not run;
- rollback method;
- cross-repository order;
- residual risks;
- documentation impact.

Checks run again after the final edit. A successful run on another SHA is not evidence for the current PR. Review the final diff; no GitHub approval count or second human reviewer is required.

## Stacked pull requests

In a linear stack, each pull request is based on the preceding branch. Until the stack lands, use merge commits that preserve provenance:

```text
merge the bottom pull request into dev
→ keep its branch until the child pull request lands
→ retarget the next pull request to dev
→ inspect the new aggregate diff
→ repeat CI and review
```

When squash or rebase is used, every child PR is rebuilt on new `dev` and receives fresh CI and review; previous results do not carry over.

## Fix forward

An error is corrected through a new work PR into `dev` and promotion into `main`, or an administrator's documented emergency bypass. A revert commit is an available rollback; permanent branch history is never rewritten. This adds no staging environment: ADR-0084 still defines one deployed environment.

A release is not a consequence of merging: it is a separate operation with its own owner authorization.

## Cross-repository changes

Do not combine in one merge:

- a provider implementation change;
- private harness checks;
- a provider artifact release;
- promotion of a pinned version in the private setup-system authoring environment;
- promotion of the provider manifest in `ai_stp`.

The pull request documents the order and compatibility window. Each repository gets a separate pull request and its own checks.
