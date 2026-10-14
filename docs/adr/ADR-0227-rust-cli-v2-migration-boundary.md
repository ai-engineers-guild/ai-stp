---
description: "One native CLI engine, explicit legacy writer transfer, and owner-bound standalone release distribution."
last_verified: "2026-10-14"
---

# ADR-0227: Native CLI and production writer transfer

Status: accepted; implemented in `apps/cli-v2`.

## Context and decision

The owner requested a clean Rust implementation and a controlled switch of the
public `ai-stp` command. The historical 245-command Python inventory is reconciled
by [business outcome](../engineering/cli-v2-scope.md), not translated module for
module. Corporate workflows, harness executable management, automatic backups
and model interfaces are excluded. The backend is not part of this rewrite.

One Cargo package contains a headless library and a thin executable. Modules own
business capabilities; expert commands and durable tasks call the same services
in process. One executable registry owns parsing, machine help and capability
reporting. Unsupported operations refuse explicitly. There is no Python fallback,
generic plugin framework, background update service or second business engine.

Envelope v1, `/v1`, provider protocol v3 and canonical object identities remain
compatible. The public executable is `ai-stp`; the internal package/directory
name and durable namespace markers are preserved to avoid an unrelated storage
migration. The old source remains a development compatibility oracle; it is not
included in native distribution artifacts. Desktop bundles Rust and communicates
only through the CLI machine contract (ADR-0222).

## Installation components and platform boundary

Public setup-system repositories release ai-stp installation components
(ADR-0228). Their authenticated executables alone write final harness state.
The managed release is resolved before planning; retained operations remain bound
to their original exact component. Native verification enforces full publisher
identity, signature, environment, digest, profile and protocol checks without a
Python verification runtime. An unsupported object or platform is a refusal,
not a weaker verification path.

The CLI observes user-installed harness programs and binds their identities to
compatibility checks, without owning their installation or updates (ADR-0232).
Linux implements isolated provider execution, coordinated one-to-three-root
configuration and staged active-consumer handoff. The owner accepts successful
macOS/Windows CI for their release artifacts without requiring a new provider
sandbox port. Their provider execution stays unavailable and is reported as such.
Build success is not evidence for an unimplemented installer.

## State, credentials and recovery

State resolution is explicit `--state-dir`, then `AI_STP_STATE_DIR`, then the
existing XDG data layout. Metadata/read commands create no state. Explicit `init`
creates a private directory and uses the existing identity plan/apply journal;
replay preserves the key and a changed credential backend refuses. Existing
Python identity/database files require an explicit migration, never initialization
as a second owner. Credentials stay in the selected native keyring or explicitly
chosen Unix private-file backend, with no automatic fallback.

`state migrate plan` binds physical root/database identity, complete row generation,
owner/device/key, session metadata and the explicit original backend/provider.
Unfinished legacy operations, tasks, installation/self-update journals and browser
login refuse. Apply preserves the same database inode, all 51 tables and existing
rows. Admission atomically stamps schema 54 and its operation to fence old
schema-53 writers. Native ownership stays pending until the key/session have been
copied, read back and retired from their old slots. Ordinary commands refuse
pending ownership; the retained plan owns forward recovery after interruption.
Completed migration replay preserves later native writes. Historical settled
tasks remain readable without becoming native execution payloads.

Fresh native registries keep the schema-53 data model. SQLite I/O remains
relative to held directory/file capabilities through the safe VFS bridge. Native
and standard SQLite-compatible exclusive locks last until connection close;
WAL indices stay in memory and no disk temporary database is introduced. Schema
comparison ignores only ASCII whitespace outside quoted literals/identifiers.
Never use an immutable/main-file-only view as a live-WAL transfer source.

No automatic database/configuration copy, snapshot or backup is created. Recovery
uses the current state and retained intent. Older binaries must not restore a
prior database over later configuration or registry changes. Active harness
replacement is staged and confirmed from the restarted consumer (ADR-0150).

## Native executable ownership

Stable archives bind the source commit, platform, binary, license and SBOM digests.
A separate attestation job executes no repository code. Users verify release
provenance before running the extracted executable. `cli install plan/apply/status`
then installs it into a dedicated private native-owned prefix. The plan binds the
parent identity, previous receipt and exact new binary/platform/version. A durable
intent precedes atomic replacement; readback precedes its final receipt.

Updates use that same flow from the new verified archive. The CLI does not
replace a uv/pipx/system/desktop-owned launcher, change PATH, download background
updates or downgrade a version. Retiring a previous installer and exposing the
new command are explicit deployment operations. Interrupted replacement resumes
without restoring user state; Windows can require old processes to exit first.

## Validation and consequences

The native gate covers canonical and envelope compatibility, real SQLite/WAL,
bounded filesystem/process/HTTP behavior, refusal and recovery, and an optimized
release build. Migration proof terminates a real process after admission and
key transfer, resumes the same operation and verifies subsequent native writes.
Archive tests distinguish a modeled publication checkpoint from an OS crash.
Platform CI runs extracted artifacts outside the checkout without Python on PATH.
Desktop verifies the actual bundled native executable under its filtered environment.

Release performance is measured on optimized builds with an isolated home;
command counts and debug timings are not acceptance evidence. Exact successful
runs and deployed identities belong to the source PR and release. Preserve
`main` and `dev`, promote verified same-repository heads, and never describe
queued/skipped checks as successful qualification.
