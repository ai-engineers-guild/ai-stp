---
description: "Decision to ship the user-facing CLI as one Python distribution that acquires its attested provider."
last_verified: "2026-09-03"
---

# ADR-0146: The user-facing CLI is one Python distribution that acquires its provider

Status: accepted.

## Context

`0.0.16` published six aligned Python distributions. A user who ran
`uv tool install ai-stp-cli` received five additional `ai-stp-*` projects as
exact pins. That matched the monorepo's internal module boundaries, and it
made a fresh install depend on every internal project remaining on the index
at the same version.

`ADR-0048` separated candidate construction from publication and recorded a
five- then six-package closure. `ADR-0142` made `0.0.16` the first supported
alpha line and kept that six-package publication. Both named a single Python
distribution as a reconsideration condition.

The same install still required the user to obtain a provider before
`install plan`. `provider fetch` already bound attested GitHub release bytes
and wrote `release.json`. Telling every first-time agent to run that command
separately made one product look like two installs.

## Options

1. Keep six published distributions and document the provider fetch step.
2. Collapse internal packages into one source tree and one module.
3. Keep the workspace module boundaries, publish only `ai-stp-cli`, bundle
   those modules in its wheel and sdist, and acquire a missing attested
   provider on the first plan/install operation.

## Decision

**The public install is one distribution, `ai-stp-cli`.** Internal namespaces
`ai_stp_foundation`, `ai_stp_passports`, `ai_stp_assurance`, `ai_stp_contracts`
and `ai_stp_sources` remain separate packages in the workspace for API,
platform, worker and tests. They are not published as part of this release
line. The published wheel and sdist contain those runtime modules. Wheel
metadata has no `Requires-Dist` for the former internal `ai-stp-*` projects.
API, worker and platform stay deployment workspace members.

**Candidate construction, SBOM, checksums, double-build comparison, clean
install verification and `publish-pypi.yml` operate on that one distribution.**
The Trusted Publisher identity is this repository, workflow `publish-pypi.yml`,
environment `pypi-cli`. Publication order across internal packages disappears
because there are no internal packages on the index for a new install to
resolve.

**A missing managed provider is acquired through the existing
`attested_bind.GithubReleases` path.** Explicit `--provider`, configuration,
a remembered chosen installation and a single discovered managed executable
still win, in that order. Ambiguity, an explicit foreign path, and
`--unverified-provider` without a named executable remain refusals.
Auto-acquisition never becomes `--unverified-provider`. Trust, platform,
attestation, digest and network failures stay typed refusals; `provider fetch`
remains the explicit repair and preload command.

**PyPI provider wheels and crates.io builds are not this path.** `ADR-0141`
still owns index provenance as a future verified fallback. Locally compiled
crate bytes are not the attested GitHub asset.

**`0.0.16` remains the first supported alpha line.** `0.0.17` continues it.
Historical six-package artifacts stay immutable. `ai-stp-sources` is removed
from the index only after an independent clean install of `ai-stp-cli==0.0.17`
and provider-acquisition evidence pass. The other four historical projects may
remain as artifacts.

This supersedes the six-package publication closure in `ADR-0048` and
`ADR-0142`. It does not supersede two-stage build/publish authority, PEP 740
provenance for this CLI, or provider attestation policy.

## Consequences

- Workspace members keep their architectural boundaries; packaging is not
  permission to merge domain layers.
- `uv tool install ai-stp-cli` is a complete first-party Python install.
- Release runbooks, the candidate builder and the upload workflow name one
  project.
- Install plan and apply no longer require `--provider` when the attested
  OpenNetwork provider can be acquired or already sits in the managed root.
- Tests that assumed six `Requires-Dist` pins and a required `--provider` on
  plan/apply must follow this decision.

## Revisit conditions

Revisit before beta or GA, if a second user-facing Python distribution is
required, if provider acquisition must use PEP 740 as the default channel, or
if build/publish authority is no longer split.
