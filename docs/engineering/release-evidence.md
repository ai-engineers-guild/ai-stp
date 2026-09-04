---
description: "Required release evidence for the CLI, platform, and providers."
last_verified: "2026-09-04"
---

# Release evidence

## Common record

Every release records the repository, ref and SHA, version, artifact hash and provenance, schema versions, exact commands and results, skipped checks, final diff, working-tree state, migration, rollback, and known limitations.

An old CI run on a different SHA is not evidence. A skipped line receives `not_verified`, not success.

## CLI

A clean installation using the published command, Python 3.12 and 3.14 on Linux
x86_64, an offline path, removal and reinstallation, reference JSON, and verification
that no secrets are present are required. The CLI surface is proven on Linux,
macOS, and Windows (`ADR-0113`). The provider half of `ADR-0062` remains: a
provider platform that was not exercised is not called supported.

The Python candidate is one `ai-stp-cli` wheel and sdist: first-party modules
ship inside that wheel, metadata has no `Requires-Dist` for former internal
`ai-stp-*` projects, and the artifact is reproduced byte-for-byte with package
metadata, LICENSE, a deterministic CycloneDX SBOM, `release-manifest.json`,
`SHA256SUMS`, and provenance for the exact SHA (`ADR-0146`). A dirty candidate,
skipped attestation, or a workflow that exists but has not run successfully
receives `not_verified`.

Installation evidence records the PEP 610 provenance of that CLI wheel as a
direct source and proves the bundled modules are present as modules, not extra
distributions. `--find-links` without a direct binding is insufficient: a
matching version might resolve from the public index. The check runs machine
commands outside the source tree and confirms removal of the program. Each row
of the Python matrix must use a job-local `UV_PROJECT_ENVIRONMENT` and verify
the actual Python version from the installed CLI's response; one persistent
`.venv` is not evidence for two versions. The publication procedure lives in
[`docs/operations/runbooks/pypi-release.md`](../operations/runbooks/pypi-release.md).

## Platform

PostgreSQL migrations, user isolation, object authorization, RustFS operation, job idempotency, mixed API versions, administrator audit, backup, and restore are required.

## Provider

The exact public source, release artifact and manifest, trust policy, signature, hash, rollback protection, public checks, closed conformance verification, malicious packages, no-change plan, apply, launch, status, and restore are required.

All **seven** `NDDev-OpenNetwork/*-setup-system` providers are in scope, each
release carrying six native binaries and `SHA256SUMS`. A platform that was not
exercised is not called supported.

### The evidence slices, and who invokes each

A script nobody can run is not a check. Every slice below has a recipe, and the
recipe is where a reader learns the slice exists; none of them enters
`just check`, because the repository gate may not depend on another party's
release network or on a deployed environment being reachable.

| recipe | question it answers |
|---|---|
| `just evidence-live` | the deployed catalogue, anonymously, with no credential |
| `just evidence-providers <tag>` | does the projection table still agree with the providers **as released** |
| `just evidence-software <tag>` | can a consumer drive a released provider through `harness install/status/update/remove`; pass `acquire=1` to omit provider paths and prove transparent attested acquisition plus reuse |
| `just evidence-config <tag>` | can a native surface be captured, installed into a target, observed and removed again — one row per harness; `from_import=1` captures the whole root through `setup import` instead of `component adopt`, and both paths must end in the same observed target; `scope=project` seeds the indexed workspace instead of the harness home and installs with `--scope project`, and `scope=user_root` seeds the shared `~/.agents/skills` and installs with `--scope user_root`, each for the harnesses whose released provider declares a rule at that scope |
| `just evidence-contribution <tag>` | `#54`'s acceptance: one MCP component in each of its three native forms, and the refusal that is also an answer; each installed form is then removed again, and the owned-file form must leave the host file behind with the person's own key — the target's `config.toml` is seeded with that key before the install, so the removal has something to keep |
| `just evidence-citations` | is every source link the harness catalogue cites still alive |
| `just evidence-sync <home_a> <home_b>` | two devices, rewind, conflict and merge — needs a real browser login |
| `just evidence-publication <home>` | publication, grants, reports and owner reads — needs a real browser login |

`software-evidence` and `config-evidence` are the two workflows that run their
slice on all six native legs (`ubuntu-24.04`, `ubuntu-24.04-arm`,
`macos-15-intel`, `macos-15`, `windows-2025`, `windows-11-arm`). They are
`workflow_dispatch` only and take the exact provider tag as input.
`software-evidence` takes `transparent_acquisition` to make `harness install`
acquire and remember the attested release while every later lifecycle command
omits `--provider` and `--provider-manifest`; the report verifies that the
managed release retained the requested exact tag. `config-evidence` also takes
`from_import` to drive the import capture path.

## First public catalog

The launch-catalog composition is a release barrier under `ADR-0034`, not a schema invariant. The first public release requires an inventory:

- one baseline setup each for Claude Code, Codex, Pi, OpenCode, and Grok Build;
- role families were removed from the barrier by the 2026-08-28 amendment to `ADR-0034`: their source is archived, there is no live repository from which to rebuild them, and provenance inside a content-addressed passport cannot be repaired by an edit;
- reusable first-party components sufficient to build these setups;
- every launch object is published from a verified AI Engineers Guild namespace with a complete passport, provenance, current required evidence, and compatibility and installation evidence;
- launch-catalog object content— instructions, descriptions, and components—is maintained in English under `ADR-0035`;
- every exact launch-catalog reference resolves, and no object has expired or missing required evidence.

Guild owners divide the role families among themselves, and peer review of every launch object is mandatory. Baseline setups for beta harnesses are minimal: definition, installation, and an honest label below the primary support tier; the depth of Pi, OpenCode, and Grok Build does not block the release. Specific object content is created during the content phase against real harnesses and is not fixed here.

## Release lines

The first MVP release is blocked by completeness of the product requirements for the core, local environment, server, and web; complete end-to-end evidence for Claude Code and Codex across the declared matrix; and the populated launch catalog described above.

The Pi, OpenCode, and Grok Build lines advance independently and do not block the first release. Incomplete beta evidence is grounds neither to delay the release nor to declare the beta line supported: a line without a recorded run receives `not_verified`.

## Blocking conditions

A release is blocked by an unresolved priority-one finding, an outdated pinned provider version, a missing source artifact, a schema-documentation mismatch, a dependency vulnerability above the approved threshold, or missing recovery instructions.
