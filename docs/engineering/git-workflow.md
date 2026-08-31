---
description: "Rules for branches, commits, pull requests, and cross-repository changes."
last_verified: "2026-08-12"
---

# Git workflow

## Branches

`main` is the repository's only line: it is the default, integration, and release branch. Implementation pull requests target it. There is no separate integration branch.

This was not always the case: `dev` used to be the integration branch, and moving from it to `main` required a separate promotion with a second review. That step caught nothing: `main` was unprotected, no checks were required, and promotions accumulated for weeks before landing as one pull request containing hundreds of commits. The second branch path cost more than it provided and was removed.

Contributors work in personal branches:

- `rldyourmnd` — Danil's personal working branch; Danil owns the project;
- `letya999` — Artem's personal working branch.

Each contributor writes only to their own personal branch and keeps it current by merging `main` into it. A completed change goes from the personal branch to `main` in a pull request; after green CI on the exact HEAD, the author lands it with a merge commit. Contributors perform integration together, each for their own work.

When CI is unavailable, evidence is a complete `just check` run on the exact
HEAD. Its output—commands run, test count, and coverage—is recorded in the merge
commit message. This substitutes the evidence, not the requirement: merging
without any run is never allowed. This rule is written here because the runner
has already been unavailable and merges proceeded this way; a silent mismatch
between practice and the rule is worse than either explicit option.

The project owner may merge another contributor's pull request when the author
would otherwise remain blocked. In that case, the person merging resolves the
conflicts.

After a pull request is merged, GitHub automatically deletes its branch on the origin. The personal branch continues locally: merge the latest `main` into it and publish it again with a normal push. Disabling automatic deletion requires repository administrator rights.

```text
rldyourmnd (Danil)      letya999 (Artem)
        \                   /
      PR to main after green CI
                ↓
               main
```

Personal branches are not the integration source of truth: a change enters the product only when merged into `main`.

The repository has several contributors. This does not contradict the single-user product model in `docs/product/vision.md`: that document describes whom the product serves, while this one describes who writes it.

A significant change starts with a draft pull request from a personal branch to `main`, so its direction is visible early. Contributors prohibit force-rewriting `main` history and deleting the branch by agreement; the platform does not currently enforce this, for the reason documented in `quality-gates.md`.

The history-rewrite prohibition applies to `main`. A personal branch belongs to its owner: they may rebuild and republish it, but nobody touches another contributor's personal branch.

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

Checks run again after the final edit. A successful run on another SHA is not evidence for the current pull request. Independent review is required; any later change makes the previous approval stale.

## Stacked pull requests

In a linear stack, each pull request is based on the preceding branch. Until the stack lands, use merge commits that preserve provenance:

```text
merge the bottom pull request into main
→ keep its branch until the child pull request lands
→ retarget the next pull request to main
→ inspect the new aggregate diff
→ repeat CI and review
```

When squash or rebase is used, every child pull request is rebuilt on the new `main` and receives fresh CI and review; previous results do not carry over.

## Fix forward

An error in `main` is corrected by the next pull request, not by rewriting history or reverting the branch. There is no second path that could catch it earlier—this is the deliberate tradeoff in `ADR-0084`, whose cost is that response speed matters more than a tidy rollback.

A release is not a consequence of merging: it is a separate operation with its own owner authorization.

## Cross-repository changes

Do not combine in one merge:

- a provider implementation change;
- private harness checks;
- a provider artifact release;
- promotion of a pinned version in the private setup-system authoring environment;
- promotion of the provider manifest in `ai_stp`.

The pull request documents the order and compatibility window. Each repository gets a separate pull request and its own checks.
