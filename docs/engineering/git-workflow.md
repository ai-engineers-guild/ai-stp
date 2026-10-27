---
description: "Branch integration, exact-head qualification and release promotion."
last_verified: "2026-10-15"
---

# Git workflow

CI push branches: `main`.

The `check` workflow runs a finite PR integration phase: redacted secret
scanning with scanner controls, Python/docs syntax and source contracts,
non-database unit tests, web/Desktop types and units, and native library analysis
and units. CodeQL analyzes each public candidate and waits for processed findings.
A PR proves integration eligibility; it does not claim packaged runtime acceptance.

Integrated `main` pushes run the complete repository matrix plus the existing
Desktop, CodeQL and native archive workflows. Full native builds, database
scenarios, browser/SDK matrices, package consumption and installed target acceptance
remain here. `dev` pushes do not repeat source builds. Impact is currently
conservative: every main candidate selects the full contract. Manual diagnosis
also selects the full contract and cannot promote production.

Registered native experiments join the same final qualification through their
owning reusable workflow. Main and manual qualification run every registered
experiment. PRs run an experiment when its source, pinned toolchain or GitHub
automation changes; an unchanged owner is explicitly skipped. Unknown or missing
native probes refuse selection until an owner is registered. The WASIp2 experiment
executes one identical component on Linux, macOS and Windows; it does not enable a
production provider backend. Source selection does not waive common PR checks.

The final `qualification` depends on every owning job and requires successful
results for the selected phase and explicit skips for the other phase. Failure,
cancellation, missing work and an unexpected skip or run refuse. Public source
qualification also refuses open code-scanning findings for the validated ref after
SARIF processing. Independent scheduled CodeQL and explicit release dispatches
retain their owners.

Both branches are permanent locally and remotely. `main` is the default protected
release branch; `dev` integrates work. Create a work branch from current `dev`
using `feat/`, `fix/`, `refactor/`, `docs/`, `test/` or `chore/`. Dependabot heads
are accepted only for verified same-repository bot PRs.

1. Implement, run affected checks, regenerate artifacts and review the diff.
2. Stage intended paths and make atomic Conventional Commits with the user's
   existing global Git identity; no author overrides or invented attribution.
3. Open a PR into `dev`. Record exact base/head, behavior, integration checks/results
   and rollback. Merge with a merge commit after green exact-head PR qualification.
4. Promote same-repository `dev` into `main` by PR and current PR qualification.
   Complete main validation must pass before the deployment ref can advance.
5. Synchronize local branches and return release merge history to `dev` through
   a PR. Remove only merged temporary branches owned by this work.

Never force-push or delete permanent branches. Existing administrator bypass
permits exceptions but does not substitute for evidence. No mandatory human
approval count applies. Rule sources live in `.github/*ruleset.json`; live GitHub
settings determine enforcement. The permanent-branch rule source requires
up-to-date `qualification` and CodeQL results; apply it only after the candidate
workflow has qualified, and read back the live rules. Production promotion checks
the current successful main run/attempt and its completed qualification before
advancing the deployment ref. Dependabot updates target `dev`; default-branch
security PRs must be retargeted or transferred before normal promotion.

If GitHub CI is unavailable, a complete `just check` on the exact head may supply
the evidence; record the commands and results in the merge. Correct mistakes with
a follow-up PR or revert commit. Publishing a release remains an explicit task.

Setup-component changes, artifact releases and consumer pin updates are separate
repository operations, each qualified before the dependent change lands.
