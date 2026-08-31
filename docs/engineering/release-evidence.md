---
description: "Required release evidence for the CLI, platform, and providers."
last_verified: "2026-08-04"
---

# Release evidence

## Common record

Every release records the repository, ref and SHA, version, artifact hash and provenance, schema versions, exact commands and results, skipped checks, final diff, working-tree state, migration, rollback, and known limitations.

An old CI run on a different SHA is not evidence. A skipped line receives `not_verified`, not success.

## CLI

A clean installation using the published command, Python 3.12 and 3.14 on Linux
x86_64, an offline path, removal and reinstallation, reference JSON, and verification
that no secrets are present are required. Under `ADR-0062`, macOS is not part of the
current support matrix.

The Python candidate additionally carries aligned versions of five public packages,
byte-for-byte reproduced wheel/sdist artifacts, package metadata and LICENSE, a
deterministic CycloneDX SBOM, `release-manifest.json`, `SHA256SUMS`, and provenance for
the exact SHA. A dirty candidate, skipped attestation, or a workflow that exists but
has not run successfully receives `not_verified`.

Installation evidence additionally records the PEP 610 provenance of all five internal
wheels supplied from direct sources. Installing only the CLI wheel with `--find-links`
is insufficient: matching internal versions might have resolved through the public
index. The check runs machine commands outside the source tree and confirms removal of
the program. Each row of the Python matrix must use a job-local
`UV_PROJECT_ENVIRONMENT` and verify the actual Python version from the installed CLI's
response; one persistent `.venv` is not evidence for two versions.

## Platform

PostgreSQL migrations, user isolation, object authorization, RustFS operation, job idempotency, mixed API versions, administrator audit, backup, and restore are required.

## Provider

The exact public source, release artifact and manifest, trust policy, signature, hash, rollback protection, public checks, closed conformance verification, malicious packages, no-change plan, apply, launch, status, and restore are required.

Linux x86_64 is required for all five providers. Claude Code and Codex block the main
release; the three beta lines complete the same safe lifecycle but do not strengthen
their support label. A platform that was not exercised is not called supported;
macOS receives `not_verified` and does not block the current release.

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
