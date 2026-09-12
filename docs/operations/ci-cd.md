---
description: "Public repository checks, pull deployment, and exact-artifact release order."
last_verified: "2026-09-10"
---

# CI and releases

The public repository `ai-engineers-guild/ai-stp` owns executable CI and production
promotion (`ADR-0109`, `ADR-0110`). The archived underscore repository runs no
workflows and cannot block this gate. Fleet classes and their availability are
not scheduling dependencies of the public product.

## Repository gate

The owner of the local gate composition is `justfile`: inspect `just --show check`
and the referenced recipes. `.github/workflows/check.yml` executes their commands
directly, with job-specific dependency setup. The workflow does not install or
invoke `just`. `tests/contract/test_gate_split_covers_the_gate.py` verifies the
relationship; `release_scripts/clean_install_regress.sh` is shared by the local
and CI installation check. Windows invokes Git-for-Windows Bash through
`release_scripts/run_bash.py`.

## Heavy validation runs in CI

The workstation commit hook is intentionally limited to fast source-level
checks and focused tests. Full documentation builds/regression, PostgreSQL and
BT backend regression, package/install regression, production web builds,
coverage suites, browser E2E, feature profiles, cross-platform matrices, and
repository-wide security scans are CI-only. They are not required or expected
before a local commit or through a pre-push hook.

`.github/workflows/check.yml` runs the heavy matrix for every pull request,
including draft pull requests, and for pushes to `dev` and `main`; `workflow_dispatch`
is available for an explicit rerun. The CI status on the exact branch SHA is
the authoritative result. This checkout has no GitLab remote and no
`.gitlab-ci.yml`, so there is no GitLab pipeline to dispatch from this
repository; a future mirror must preserve the same CI-only boundary.

All jobs use standard GitHub-hosted runners. Server tests use Linux with a real
PostgreSQL service and separate shards. CLI, web unit, browser E2E, and feature
profiles run on the operating systems in the workflow matrices. Web static
analysis, packaging, and documentation have their own jobs. Browser E2E specs
are split by the workflow's explicit shard mechanism; its matrix is the source
of the current partition, not a copied count in this document.

Independent checks do not wait for one another (`ADR-0104`, `ADR-0105`). Coverage
is the data dependency: it combines the Linux test shards' coverage files and
prints the union (`ADR-0147`). Coverage percentage does not fail the gate.
A newer push cancels the older `check` for that ref. The workflow verdict already
combines its jobs; no extra aggregation job is needed.

CodeQL is a separate public workflow using `security-extended`. It is not a
substitute for the repository security recipe or an omitted test. ADR-0180 defines
default `dev`, protected `main`, dev promotion checks and administrator bypass;
release work does not add mandatory human approvals.

## Promotion and production proof

`.github/workflows/deploy.yml` accepts only a successful `check` raised by a push
to `main`. Its `promote` job verifies the exact checked SHA and advances
`refs/heads/deploy/prod` without force. Promotion is serialized with
`cancel-in-progress: false`; a stale ancestor cannot move the ref backwards.
Only that job has `contents: write`.

The production host is not an Actions runner. Its timer runs
`deploy/pull-deploy.sh`, which fetches the public ref through anonymous HTTPS and
performs the locked local deployment (`ADR-0103`, `ADR-0109`). CI has no SSH
deployment credential; application secrets remain on the host. Deployment and
database recovery procedures belong to [the deployment runbook](runbooks/deploy.md)
and [the migration runbook](runbooks/database-migration.md).

`verify-public` has read permission and waits for `deploy/verify_public.py` to
prove the public origin's environment, schema, and served commit. A served
descendant may satisfy a promotion that a later push overtook. The timeout is
bounded in the workflow and must cover the measured serialized image-build and
migration duration; an immediate read proves only whether a deployment already
finished. A green promotion alone is not a green production proof.

## Candidate and publication

`.github/workflows/release-candidate.yml` is dispatched on an exact version tag.
The build and attestation jobs run on separate GitHub-hosted runners: the build
has no OIDC authority, and attestation checks out no source (`ADR-0048`). The
candidate contains one public `ai-stp-cli` wheel and sdist (`ADR-0146`).
`.github/workflows/publish-pypi.yml` publishes those exact attested bytes through
Trusted Publishing. Preparation, environment checks, idempotence, and PyPI
readback belong to [the package release runbook](runbooks/pypi-release.md).

The repository gate does not depend on provider networks or a deployed account.
The inventory and meaning of release evidence belong to
[release-evidence.md](../engineering/release-evidence.md). Its current workflows
are `config-evidence.yml`, `software-evidence.yml`, and `platform-evidence.yml`.
A local or CI test of one operating system does not prove the other native
OS/architecture legs. Missing launch evidence remains `not_verified`.

## Cross-repository order

An extension of a strict reader's accepted schema ships the compatible consumer
reader first, as a released artifact. The provider writer is tagged only after
its emitted declaration passes against that installed reader. SPEC-068 follows
this order for complete native preservation. The acquisition and corpus cycle
below starts after that reader prerequisite; an older closed reader cannot gain
tolerance from a later writer release.

1. Implement and validate a provider contract change in its source estate.
2. Render and validate the affected public setup-system trees.
3. Publish immutable provider artifacts with their provenance.
4. Acquire those exact artifacts and reconcile the consumer's owned contracts.
5. Capture the corpus from exact attested releases and validate its native graph.
6. Qualify the consumer candidate, publish, and verify public/account readback.

The provider's verified `provider-info` supplies its capability declaration.
A closed authoring environment is not a dependency or runtime source.
