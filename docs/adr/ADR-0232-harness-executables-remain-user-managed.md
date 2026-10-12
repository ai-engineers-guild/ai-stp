---
description: "ai-stp observes harness executables and manages configuration, without installing or updating the harness."
last_verified: "2026-10-12"
---

# ADR-0232: Harness executables remain user-managed

Status: accepted; supersedes ADR-0122 and the harness-program lifecycle portion of ADR-0228.

## Decision

The user and harness vendor own installation, upgrades and removal of the harness
executable. ai-stp observes the installed version for compatibility, but does not
pin a desired harness version, download a harness distribution, change its update
policy, or install, update, downgrade or remove it. Missing or unknown versions
stay explicit; they never trigger an installation or a guessed version.

Native observation resolves the catalog's command on PATH, or an explicit
absolute executable, and runs only its bounded version query. The result is local
observation, not publisher attestation. Selection plans bind the observed version
and executable identity and revalidate before new effects. Vendor updates are
allowed: changed observations require replanning, never rollback of the harness.

Setup systems remain ai-stp configuration components with their existing
repositories and isolated provider boundary. Exact setup, component and provider
versions, artifact digests and provenance checks remain required. Generic `cli`
components and ai-stp's own updates are different subjects and are unchanged.

## Migration

Remove native program mutation and vendor acquisition commands and the production
`harness` command family. Production discovery remains `toolchain harnesses`;
native discovery is `program status`. Environment inspection reports the installed
harness without suggesting an ai-stp harness installation command.

Preserve existing files, operation history and historical wire schemas. Old
harness mutation plans cannot acquire new effects through this release. Users
manage previously installed executables too; upgrading ai-stp neither deletes nor
adopts them. Selection plans carrying the retired `program_prefix` input must be
recreated using current observations. No database migration is required.

This correction does not itself establish Rust production parity. The executable
registry and code-adjacent contract define implemented native support; outstanding
configuration coordination and cutover evidence retain their existing owners.
