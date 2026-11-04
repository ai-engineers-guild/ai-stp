---
description: "Where native release and deployment evidence is produced and verified."
last_verified: "2026-11-04"
---

# Release evidence

The native release workflow is `.github/workflows/cli-release.yml`. Stable tags
are `cli-v<version>` and match Cargo metadata. The workflow builds and attests
the archives, wheels, crate and checksum files. Verify and publish those exact
files in the GitHub release, then publish the same wheels and crate through the
registry workflows. GitHub retains the source and qualification evidence.

Both client release owners recheck the exact currently qualified main through
`require-client-release-source.sh`. A successful source build, historical run
or separately named preflight artifact cannot replace the owning main
qualification or the installed release-package evidence.

`just cli-check` exercises native formatting, Clippy, tests, optimized build and
real JSON/SQLite regression. CI runs on Linux, macOS and Windows. Archive proof
uses the extracted executable outside the checkout with an isolated home and PATH.
A compiled platform is not evidence for unsupported provider execution; the
[CLI guide](../../apps/cli/README.md#release-and-supported-platforms) states limits.

`just --list` lists optional `evidence-*` recipes for deployed account, catalog,
publication, configuration and provider operations. Inspect the recipe before use:
connected evidence may require a signed-in state and explicit write authority.
A skipped or unavailable scenario remains unverified. These recipes are outside
`just check` because a third-party network or deployed service may be unavailable.

For deployment, match `/v1/system/version` and settled host markers to the exact
qualified source SHA, then verify the serving source. See the
[deployment runbook](../operations/runbooks/deploy.md). Local state migration and
credential continuity require their own observed receipts; a successful version
command alone does not prove them.

The manually dispatched `desktop` workflow offers `packages_only` for compilation
diagnosis and transferring exact candidate bundles to an approved native test
host. It skips installed application journeys and publishes separately named
`preflight` artifacts with `application_acceptance=false`. This mode cannot be
selected by the reusable release owner and supplies no release qualification.
Normal main and release calls still require all installed application proofs.
