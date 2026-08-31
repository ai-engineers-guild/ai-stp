---
description: "Separation of reproducible Python candidate builds from manual OIDC publication."
last_verified: "2026-08-29"
---

# ADR-0048: Two-Stage Python Package Release

Status: accepted for the separation of authority, superseded for the executor.
The requirement—build without OIDC, attest without checkout and only with bytes from
the preceding job—remains unchanged; only the mechanism enforcing this separation
changed. The record of the executor change belongs to private infrastructure and is
not published here.

What applies in this tree: both jobs run on GitHub-hosted runners, and separation is
enforced by the job boundary rather than the machine. The persistent roles named
below, `guild-ai-stp-release-build` and `guild-ai-stp-release-attest`, were never
registered, so the workflow could not be placed on any machine—which is why the
executor changed.

## Context

Five public Python packages form one installable CLI closure:
`ai-stp-foundation`, `ai-stp-passports`, `ai-stp-assurance`, `ai-stp-contracts`, and
`ai-stp-cli`. Publishing each package with a separate local command leaves a window
in which PyPI contains an incompatible partial set. API, platform, and worker are not
user-facing PyPI packages and are not included in this release.

PyPI access must not be present in ordinary CI, a persistent PR runner, or a local
token. GitHub artifact attestation also requires OIDC and is unavailable to a private
repository on the current plan. Under the product plan, the repository becomes
public only for the first MVP release.

## Decision

The release is divided into two trust stages.

1. `release-candidate`, on a separate self-hosted runner without PyPI credentials,
   builds five wheels and five sdists twice with the same `SOURCE_DATE_EPOCH`,
   compares them byte for byte, validates metadata, LICENSE, and safe archive members,
   and creates a deterministic CycloneDX SBOM, `release-manifest.json`, and
   `SHA256SUMS`. After the build, a separate check installs the CLI outside the source
   tree and supplies all five internal wheels as direct exact sources. The PEP 610
   provenance record for every installed `ai-stp-*` package must point to the verified
   candidate bytes; `--find-links` alone is insufficient because the resolver may
   select the same version from the public index.
2. In the public repository, a separate attestation job receives **exactly** the
   artifact from the first job and issues GitHub/Sigstore provenance. The ordinary
   build job does not receive `id-token: write`.
3. PyPI publication is not part of the candidate workflow. It is added and enabled
   only after creating the protected `pypi` environment, configuring PyPI Trusted
   Publisher for the exact repository/workflow/environment, and obtaining separate
   authorization from the release owner. The publish job's only authority is a
   short-lived OIDC token; no API token or password is stored.

All five package versions must match, and dependencies within this closure are pinned
to the exact shared version. A final tagged candidate requires a clean tree and an
exact `v<version>` tag. A dirty build is allowed only through an explicit local flag
for characterization and records `dirty: true`; it does not create release evidence.

The release path has two separate physical roles. `guild-ai-stp-release-build` runs
repository build code without OIDC authority. `guild-ai-stp-release-attest` receives
only the immutable artifact from the previous job, performs no checkout, and alone
receives `id-token: write` and `attestations: write`. These roles share neither host,
user, nor filesystem with each other or with CI/deploy runners. New labels on one
machine do not create trust separation.

## Consequences

The current workflow can build and, once the repository is public, attest a candidate,
but intentionally cannot publish. Preparation for `#185` is therefore advanced, but
the issue is not closed until there is a protected environment, Trusted Publisher,
a macOS clean install, and separately authorized publication.

The publication order of the five file pairs must account for dependencies:
foundation, passports, assurance, contracts, CLI. After a partial failure, an already
uploaded version is not overwritten; the fix receives a new version. Yank is used
only as an operator signal and does not delete historical bytes.

## Reconsideration Conditions

The decision will be reconsidered upon moving to a single Python distribution
artifact or to an external release controller with equivalent short-lived identity
and provenance.
