---
description: "Native archive-owned CLI installation and forward update recovery."
last_verified: "2026-10-14"
---

# CLI installation and updates

ADR-0227 supersedes the Python wheel updater for the native distribution.
`apps/cli-v2/src/distribution.rs` owns `cli install plan`, `apply` and `status`.
The same flow installs or updates a verified native archive. It does not download
releases, mutate PATH, run another package manager or manage a harness executable.

Run the new executable outside the intended dedicated prefix. Its plan binds the
physical parent, current release receipt, old/new binary digests, version and
platform. Unowned/shared prefixes, external drift and downgrades are rejected.
Apply takes the exact saved plan and digest, revalidates preconditions and
persists admission before atomic binary replacement. Binary readback precedes
publication of the final release and receipt records.

Status exposes a pending plan for forward recovery. An admitted plan survives
expiry; after binary publication recovery does not require the original archive
path. A completed replay verifies the retained result. Windows may require the
old executable process to exit before replacement can proceed.

The prefix contains only its ownership marker, lock, binary and bounded operation
records. Application state and credentials are independent. Retire a previous
uv/pipx launcher through its owner before exposing the native command. Existing
Python state transfers separately through `state migrate plan/apply/status`.
There are no update-notice checks, automatic backups, wheel rollback or implicit
registry restoration in the native updater.

[Native installation reference](../../apps/cli-v2/README.md) describes archive
verification, platform support and the exact command sequence. Published release
assets bind their source commit, target, checksums, manifest and SBOM, with GitHub
artifact attestation from `.github/workflows/cli-release.yml`.
