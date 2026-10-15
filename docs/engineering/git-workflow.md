---
description: "Branch integration, exact-head qualification and release promotion."
last_verified: "2026-10-15"
---

# Git workflow

CI push branches: `dev`, `main`.

Both branches are permanent locally and remotely. `main` is the default protected
release branch; `dev` integrates work. Create a work branch from current `dev`
using `feat/`, `fix/`, `refactor/`, `docs/`, `test/` or `chore/`. Dependabot heads
are accepted only for verified same-repository bot PRs.

1. Implement, run affected checks, regenerate artifacts and review the diff.
2. Stage intended paths and make atomic Conventional Commits with the user's
   existing global Git identity; no author overrides or invented attribution.
3. Open a PR into `dev`. Record exact base/head, behavior, checks/results and
   rollback. Merge with a merge commit after green exact-head checks.
4. Promote same-repository `dev` into `main` by PR and exact-head checks.
5. Synchronize local branches and return release merge history to `dev` through
   a PR. Remove only merged temporary branches owned by this work.

Never force-push or delete permanent branches. Existing administrator bypass
permits exceptions but does not substitute for evidence. No mandatory human
approval count applies. Rule sources live in `.github/*ruleset.json`; live GitHub
settings determine enforcement. Dependabot updates target `dev`; default-branch
security PRs must be retargeted or transferred before normal promotion.

If GitHub CI is unavailable, a complete `just check` on the exact head may supply
the evidence; record the commands and results in the merge. Correct mistakes with
a follow-up PR or revert commit. Publishing a release remains an explicit task.

Setup-component changes, artifact releases and consumer pin updates are separate
repository operations, each qualified before the dependent change lands.
