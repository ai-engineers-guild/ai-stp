---
description: "SPEC-068: Preserve an existing harness setup and restore its complete native state."
last_verified: "2026-09-07"
---

# SPEC-068: Preserved native setups

## Purpose

A user arrives with a working harness, acquires a different setup, uses it, and
can return to the complete setup that was present before installation. Existing
user configuration is itself a setup, not a disposable collection of files.

## Scope

Included: complete native capture, a local setup identity, verified provider
backup linkage, installation prerequisites, preservation before switching,
exact restoration, interruption recovery and machine-readable agent actions.
One setup belongs to one harness. Coordination of several harnesses retains
separate setup identities. Public/private distribution belongs to SPEC-026;
the server implementation is maintained independently from the CLI.

## Terms

Preserved setup means a local setup identity bound to a retained native
snapshot. Snapshot means provider-owned recovery bytes with measured coverage
and integrity. Installation ownership and preservation coverage are distinct:
configuration can require preservation without becoming a portable write route.

## Requirements

- `REQ-6801`: Before replacing a harness configuration, preserve its complete
  current setup under a stable local setup identity. Empty native configuration
  is a valid original state. The selected setup must not overwrite an original
  that has no verified recovery path.
- `REQ-6802`: Capture accounts for every file and native contribution in the
  chosen harness scopes. Complete means complete against the measured native
  surface, including user additions outside the previous provider ownership
  list. Unreadable or unsupported configuration blocks replacement rather than
  silently yielding a partial original setup. Documented companions are explicit:
  a global `.claude` target also covers its sibling `.claude.json`, and no other
  sibling paths.
- `REQ-6803`: A provider backup reference is accepted as recovery evidence only
  after the provider verifies its existence, integrity and binding to the
  captured target. The local setup and backup are distinct identities with an
  explicit relationship. A string matching a reference pattern is insufficient.
- `REQ-6804`: Preserved setups remain discoverable and selectable through CLI
  machine output after a process restart. The output identifies the source
  harness and scope, capture time, completeness and actual restoration status.
- `REQ-6805`: Restoring a preserved setup restores its exact native file bytes,
  paths, supported permission metadata and contributions. Native configuration
  added after capture is removed from that restored setup after first being
  preserved as the current setup. Files outside the selected harness surface
  remain untouched. Preservation does not expand installation ownership; return
  retains the prior installed setup's version, component and bundle identity.
- `REQ-6806`: Every switch, including return to an original setup, preserves the
  current configuration first. User edits made while using an installed setup
  survive as a selectable captured setup. Repeating a completed switch does
  not create another effect or another copy of the same captured graph.
- `REQ-6807`: A saved setup pins its recovery bytes against automatic retention
  while it depends on them. Missing, damaged or incomplete recovery bytes make
  restoration unavailable with a typed reason; the CLI must not install a
  default setup or claim a successful return instead.
- `REQ-6808`: Plans bind source and destination setup identities, native scopes,
  exact target observations, provider identity and recovery effects. Changes
  after planning invalidate the plan before replacement. Lost processes are
  recovered from durable state without guessing whether an effect happened.
  A lost response may recover the saved setup identity from fresh, bound
  provider evidence without repeating target effects or changing a terminal
  partial installation into a verified one. Plans also bind the relative-path
  base. Recovery before journal commit restores previous provider metadata,
  including its original absence.
- `REQ-6809`: Restored success requires a fresh measurement of the complete
  covered native state against the original capture. Comparing only previously
  managed files cannot prove complete restoration.
- `REQ-6810`: Local recovery bytes do not become a portable public passport.
  Credentials, login state and private runtime data retain their existing
  storage boundaries; portable component metadata cannot disclose them. Mixed
  native configuration may remain in protected local recovery storage, but its
  contents never enter portable metadata, CLI output or publication.

## States and errors

Installation and recovery retain SPEC-008 and the operation contract as state
owners. Capture reports complete, incomplete or unavailable; recovery evidence
reports verified or unavailable with a reason. No outcome is labelled restored
while any covered native state differs or remains unmeasured.

## Security and privacy

The provider and CLI retain their existing release, isolation and active-target
checks. Native configuration bytes remain in protected local recovery storage.
The `parent` base is restricted to Claude's declared companion cover; arbitrary
ancestor or sibling coverage is refused. Product credential files and declared
runtime state are excluded; their
transport directories retain current metadata. Shared native state is an
explicit effect and cannot be silently assigned to a different harness.

## Compatibility and migration

The consumer migrates the local registry to add saved setup identities while
retaining existing operation history. Old mutation snapshots remain readable
but cannot be labelled complete without verified coverage. Old provider readers
must refuse new complete backup formats instead of interpreting a different
coverage base as a legacy payload. The protocol reader
and provider kit accepting the new request capability and status metadata ship
before the provider writer. Downgrade preserves the registry and backup pools;
saved recovery bytes are not discarded to accommodate an older reader.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-6801` | Populated and empty original configurations survive install and return; failed preservation performs no replacement. |
| `REQ-6802` | Native scripts, extensions, contributions and user-added configuration are included; unreadable and unsupported members cannot disappear from the completeness result. |
| `REQ-6803` | Real provider accepts the correct target-bound backup and refuses missing, corrupt, incomplete and foreign references. |
| `REQ-6804` | A fresh CLI process lists the original setup and resolves the same restoration identity. |
| `REQ-6805` | Byte/path/mode inventory before installation equals the restored inventory; additional native members disappear while unrelated project files remain. |
| `REQ-6806` | Edits made under the selected setup remain selectable after restoring the original; retry creates no duplicate effect. |
| `REQ-6807` | Retention does not remove a referenced capture; damaged or missing bytes produce an explicit refusal. |
| `REQ-6808` | A stale source, target change, process kill and lost provider response leave a recoverable record and no false terminal result. |
| `REQ-6809` | Add one unexpected native file after restoration: verification must fail even when all old managed files match. |
| `REQ-6810` | Portable metadata and CLI output omit credential values and backup contents. |

## Required checks

Run `just docs-check`, `just back-check`, the affected CLI process scenarios and
the setup-provider gate. Released provider lifecycle evidence is measured
separately from offline repository tests.
