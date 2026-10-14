---
description: "Required release evidence for the CLI, platform, and providers."
last_verified: "2026-10-14"
---

# Release evidence

## Common record

Every release records the repository, ref and SHA, version, artifact hash and provenance, schema versions, exact commands and results, skipped checks, final diff, working-tree state, migration, rollback, and known limitations.

An old CI run on a different SHA is not evidence. A skipped line receives `not_verified`, not success.

## CLI

The public `ai-stp` executable is the optimized Rust engine. Its exact tag-bound
workflow builds and exercises Linux x86_64, macOS arm64 and Windows x86_64
archives. Each archive contains the native executable, license, source/target
manifest and CycloneDX SBOM; its matching checksum and GitHub attestation must
bind the reviewed source and signer. Verify the public download bytes before
installation. Compilation is not claimed to be reproducible, OS-signed or
notarized merely because the archive has an attestation.

`just cli-v2-check` proves formatting, Clippy, executable contracts, the optimized
build and real SQLite/envelope behavior. The platform jobs execute the native
operations and archive installer, including ownership, stale-plan and recovery
refusals. The [native guide](../../apps/cli-v2/README.md) owns the exact platform
boundary: provider execution, setup installation and active-consumer handoff
remain Linux-only. A component's platform artifact does not qualify the
consumer's sandbox on that platform.

Production transfer requires its own exact plan and observed receipt: retained
registry rows and identity, schema admission that fences the old writer,
credential readback and forward recovery. A fixture migration or successful
compile is not evidence that a user's current state was transferred. Retire
the old launcher through its package manager only after native installation and
transfer are verified. Never restore an older registry over native mutations.
No automatic backup or snapshot is part of this operation.

The historical Python wheel remains a development compatibility oracle. Its
old installation matrices and immutable artifacts do not qualify the native
release; the wheel publication lane is retired. The
[historical PyPI runbook](../operations/runbooks/pypi-release.md) records that
boundary. Exact publication, installed-command and deployment receipts belong
to the release and its linked completion issue, not a rolling copy here.

## Platform

PostgreSQL migrations, user isolation, object authorization, RustFS operation,
job idempotency, mixed API versions and administrator audit require evidence.
Backup and restore operations require an explicitly authorized task; the CLI
release does not create snapshots or re-enable disabled backup workflows.

## Provider

The exact public source, release artifact and manifest, trust policy, signature,
hash, rollback protection, public checks and closed conformance verification
require evidence. Exercise malicious-package refusal, no-change plans,
preparation, publication, cancellation, status, removal and interrupted-operation
recovery through the native consumer. Harness executables remain user/vendor
managed; observing their identity is not permission to install or update them.

All **seven** `NDDev-Technocracy-Archive/*-setup-system` components are in scope, each
release carrying six native binaries and `SHA256SUMS`. A platform that was not
exercised is not called supported.

### The evidence slices, and who invokes each

A script nobody can run is not a check. Every slice below has a recipe, and the
recipe is where a reader learns the slice exists; none of them enters
`just check`, because the repository gate may not depend on another party's
release network or on a deployed environment being reachable.

The older Python slices below remain callable compatibility evidence. Their
command vocabulary and passing results do not establish native release
acceptance. Native API slices bind the supplied Rust executable digest;
installation and handoff receipts must likewise identify the actual native
consumer and authenticated component artifacts.

| recipe | question it answers |
|---|---|
| `just evidence-live` | the deployed catalogue, anonymously, with no credential |
| `just evidence-providers <tag>` | does the projection table still agree with the providers **as released** |
| `just evidence-config <tag>` | can a native surface be captured, installed into a target, observed and removed again — one row per harness; `from_import=1` captures the whole root through `setup import` instead of `component adopt`, and both paths must end in the same observed target; `scope=project` seeds the indexed workspace instead of the harness home and installs with `--scope project`, and `scope=user_root` seeds the shared `~/.agents/skills` and installs with `--scope user_root`, each for the harnesses whose released provider declares a rule at that scope |
| `just evidence-contribution <tag>` | `#54`'s acceptance: one MCP component in each of its three native forms, and the refusal that is also an answer; each installed form is then removed again, and the owned-file form must leave the host file behind with the person's own key — the target's `config.toml` is seeded with that key before the install, so the removal has something to keep |
| `just evidence-citations` | is every source link the harness catalogue cites still alive |
| `just evidence-sync <home_a> <home_b>` | two devices, rewind, conflict and merge — needs a real browser login |
| `just evidence-native-sync <binary> <sha256>` | the exact optimized Rust executable against the real API: two isolated devices, transfer, merge/conflict, lost reply, device replacement and logout replay; requires `AI_STP_TEST_DB_URL` and creates/removes its own migrated database, with a seeded test web session and no production credentials |
| `just evidence-native-publication <binary> <sha256>` | native authoring and component/setup publication through the real API, queue and worker, including lost-reply continuation, exact selected private GitHub source preparation with current-access rechecks, explicit public distribution and exact visibility close/open with lost-response/session-refresh reconciliation, stale/expired refusal and historical replay, actual safety refusal, native author signatures accepted by the API, and offline receipts; requires `AI_STP_TEST_DB_URL` and the pinned safety scanners on PATH; only upstream GitHub, the test account/web approval and S3 transport are fixtures |
| `just evidence-sync-hot-paths` | the private-sync denominators `#256` R05 names: ancestor walks, common-ancestor selection, page application and cold/warm task overhead, with real sqlite statement counts; `fixture` rows are setup cost, not verdicts |
| `just evidence-publication <home>` | publication, grants, reports and owner reads — needs a real browser login |

Build the native executable with `just cli-v2-build` before the native sync
slice and pass its reviewed SHA-256. The PostgreSQL test service must allow
creating disposable databases; the slice leaves existing databases untouched.
It checks the executable digest before and after the journey and reports each
observed scenario. This API proof does not replace a deployed browser-login
check or the separate native SQLite proofs of malformed-page rollback,
immutable-version closure, tombstones and explicit event abandonment.

The native publication slice also requires an optimized executable digest and
creates/removes only its own migrated database and native roots. It creates all
passports, plans and artifacts through native commands, uses the actual worker
to produce validation and catalog outcomes, and substitutes an in-memory S3
client. Its declared fixture source coordinates establish API completeness, not
GitHub provenance. The real pinned `skill-scanner` must run for skill artifacts;
enable `AI_STP_SAFETY_EXTERNAL_CLI=1` as in the worker image and keep scanner
executables outside the sandbox's temporary mount. The slice does not downgrade
safety profiles or inject passing verdicts. Author attestations are explicitly
declared fixture evidence generated by native commands; the shared Python
signature/digest consumer and actual worker verify them. This proof does not establish deployed storage durability or production writer cutover.

Use disposable authenticated homes for the sync slice. Each invocation creates
a separate collision probe, fills its release-required declared metadata, and
adopts its native source on both devices so each has the bytes needed to
release offline. Only device A's probe identity is pushed; the peer's auxiliary
adoption remains local. Earlier probe files and versions are preserved.
The expected immutable collision
leaves device B's conflicting release intact and refuses its incoming page;
that device is retained as evidence, not silently reset for another run.

The publication slice retains its exact plan and confirmation hash before
confirming. Repeating an interrupted run resumes that plan, including while its
publication job is queued; an uncertain confirmation or a rate-limited status
read does not create another attempt. A later operator invocation can retry a
terminal failed, cancelled or stale attempt. A successful repeat needs only a
fresh status read. Grant invitations require an explicitly named recipient.
A requested publication that remains unverified returns a nonzero result;
undriven grant and report scenarios remain explicit without failing read-only evidence.

`config-evidence` runs its configuration slice on the three required native legs (`ubuntu-24.04`, `macos-15`,
`windows-2025`). Linux arm64, macOS x86_64 and Windows arm64 are not_verified
and do not delay this beta (ADR-0172). It is
`workflow_dispatch` only and takes the exact provider tag as input. Its
package-only environment installs the CLI with `--no-editable` in both `uv sync`
and `uv run`: only the wheel bundles the first-party modules (`ADR-0146`),
and an editable CLI without sibling workspace projects cannot start.
The workflow also takes
`from_import` to drive the import capture path.

## Desktop

A desktop release proves that the shell over the CLI contract builds and runs
on all three OSes: each `desktop-release` bundle leg rebuilds the frontend and
both shell/core Rust crates, builds the optimized native CLI through
`apps/desktop/scripts/build-cli-sidecar.sh`, and verifies the copied executable's
Rust runtime and registry digest. The generated `sidecar.json` binds its target,
version and SHA-256; no interpreter or Python library is packaged. The workflow runs
`apps/desktop/scripts/test-bundled-sidecar.sh`, the spawn test under the app's
filtered environment, so a bundled CLI that cannot start on a real OS does not
ship. After `tauri build`, `just desktop-bundle-test` probes the resource tree
from an extracted Linux deb, the macOS app, or an administratively extracted
Windows MSI, without installing the app. `SHA256SUMS` covers every published
artifact.

Source integration and desktop CI do not publish new desktop bundles. Earlier
desktop releases retain their original sidecars; a CLI archive release does not
silently replace those immutable downloads.

It does not prove code integrity by signature — the bundles are unsigned
(`SHA256SUMS` is the integrity record), the CI never launches the installed
application window, and there is no updater: upgrading is a fresh install.
Those remain human checks on the released bundles.

## Full-beta catalog and qualification

The current corpus inventory and its immutable publication procedure belong to
[first-party-corpus.md](first-party-corpus.md). Every exact launch reference must
resolve to the recorded bytes through the public catalog. Historical MVP subsets
are not the scope of this full beta.

Qualification follows [SPEC-061](../../specs/active/SPEC-061-estate-release-qualification.md)
and [ADR-0172](../adr/ADR-0172-beta-qualification-on-three-primary-platforms.md).
All seven harnesses remain in scope. Only the three optional platform pairs are
not_verified without delaying this beta. The active implementation and evidence
work is tracked in [implementation-roadmap.md](implementation-roadmap.md).

## Blocking conditions

A release is blocked by an unresolved priority-one finding, an outdated pinned provider version, a missing source artifact, a schema-documentation mismatch, a dependency vulnerability above the approved threshold, or missing recovery instructions.
