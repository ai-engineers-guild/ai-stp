---
description: "Where native release and deployment evidence is produced and verified."
last_verified: "2026-10-15"
---

# Release evidence

The native release workflow is `.github/workflows/cli-release.yml`. Stable tags
are `cli-v<version>` and must match Cargo metadata. The release owns archives,
checksums, manifests, SBOM and attestations; its exact source PR and workflow runs
own qualification evidence. Do not duplicate release receipts in documentation.

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
