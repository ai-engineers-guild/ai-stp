---
description: "SPEC-014: Managed toolchain and bootstrap."
last_verified: "2026-08-04"
---

# SPEC-014: Managed toolchain and bootstrap

## Purpose

After installing `ai-stp`, the user receives a reproducible toolchain for diagnostics, indexing, checks, and setup generation. Tools are installed in user directories without manual system-package configuration or mandatory `sudo`.

## Scope

Includes detecting the system, architecture, harnesses, and tools; the complete `mvp-full` toolchain profile; isolated installation; LSP and checks for Python, TypeScript/JavaScript, Rust, Go, and Dart/Flutter; analyzers for information formats and generalized safe text; the offline-operation boundary; diagnostics; updates; cache; and ownership during removal. Installation of system toolchains with administrator privileges and hidden execution of package scripts are out of scope. Harness detection on Windows is in scope and described by `REQ-1419`; installation of the toolchain itself on Windows remains out of scope.

The list of offline and network operations is owned by `docs/contracts/offline-capability.md` and is not repeated here. Specific profile tool versions are selected during implementation from supported manifests.

## Terms

- `ToolchainManifest` — the exact list of tools, versions, sources, integrity evidence, platforms, and entry points.
- `mvp-full` — the sole MVP toolchain profile, installed in full during bootstrap.
- `detector` — a declared way to detect a harness or tool without changing the system.
- `ToolchainTarget` — a versioned user directory, not a system search path.
- `ToolAdapter` — a bounded wrapper with a timeout, allowed environment, and versioned output.
- `needs_user_action` — the inability to continue safely without direct human action.

## Requirements

- `REQ-1401`: Bootstrap first detects the system, architecture, available harnesses, environments, and compatible tools without changing the system.
- `REQ-1402`: Bootstrap installs one complete versioned `mvp-full` profile in full; policy defines its contents, not the current contents of the selected project.
- `REQ-1403`: Every dependency has an exact version and source, integrity evidence, a license, and a supported-system matrix.
- `REQ-1404`: Tools are installed in a versioned user directory and invoked by exact path; the ambient `PATH` is not the source of truth.
- `REQ-1405`: Installation and update use a plan, staging directory, integrity verification, an atomic current pointer, and rollback to the previous version.
- `REQ-1406`: Package installation scripts and arbitrary bootstrap scripts are disabled by default and permitted only by a separate verified policy.
- `REQ-1407`: The `mvp-full` profile contains language servers, linters, type checkers, analyzers, and scanners for Python, TypeScript/JavaScript, Rust, Go, and Dart/Flutter; an uninstalled adapter honestly returns `not_available` with a reason.
- `REQ-1408`: Analyzers for information formats and generalized parsing of bounded safe text are included in the profile and have resource limits.
- `REQ-1409`: Tool execution uses an argument array, `shell=false`, a filtered environment, timeout, output limit, and cancellation.
- `REQ-1410`: Normal installation does not require `sudo`; a required system action returns `needs_user_action` and an exact plan without the agent obtaining a password.
- `REQ-1411`: An ownership manifest lists every created path and allows normal removal to delete the toolchain without affecting user data, targets, or backups.
- `REQ-1412`: Offline mode uses only previously verified cached artifacts and does not weaken integrity or version requirements.
- `REQ-1413`: After successful bootstrap, declared offline operations work without a network, while operations that require a network are listed separately and return a typed reason.
- `REQ-1414`: Harness and tool detection uses a bounded detector set: known executable names with a verified absolute path, a safe version query, known user configuration roots, and manifests of the selected project.
- `REQ-1415`: Each detected object's result distinguishes `installed`, `configured`, `available`, and `unknown_version`, and contains the exact version or `unknown`, source path, and reason.
- `REQ-1416`: Detection does not change the system, does not recursively scan the home directory or entire disk, and accepts an explicit path from the user.
- `REQ-1417`: Multiple installations of one harness are returned as a list; an explicitly provided path takes precedence over detected paths.
- `REQ-1418`: The environment detection result is recorded in the current device passport under `ADR-0025`; detection does not change the developer passport.
- `REQ-1419`: On Windows, the detector distinguishes CLI and Desktop surfaces and, after an unsuccessful safe version query, reads only declared bounded package manifests; the version source and structured reason remain in the result.

## States and errors

Bootstrap has `discovered`, `planned`, `needs_user_action`, `installing`, `ready`, `degraded`, `partial`, and `failed` states. A missing optional adapter produces a degraded state; an integrity mismatch, unsupported system, or unknown effect after failure blocks continuation and requires recovery.

## Security and privacy

The installer does not read secrets or send inventory to the cloud without sign-in and consent. Download redirects and archives are checked for source, size, and paths. Tool output is considered untrusted and sanitized before entering logs or agent context. A system environment is allowed only after verifying its canonical path and that other users cannot modify it.

## Compatibility and migration

The toolchain policy, manifest, and adapter output are versioned. A new toolchain is installed alongside the old one; the project index retains tool versions. Removing an old version is permitted after there are no active operations and under an explicit cleanup policy.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1401` | A clean Linux x86_64 fixture confirms detection without created files; portable macOS fixtures remain non-release regression evidence. |
| `REQ-1402` | Bootstrap in an empty project and a documentation project produces the same complete profile. |
| `REQ-1403` | Manifest validation rejects a floating source, missing integrity evidence, and an unsupported system. |
| `REQ-1404` | A process check uses the target's exact binary when `PATH` is replaced. |
| `REQ-1405` | Failure checks cover staging, pointer switching, and rollback. |
| `REQ-1406` | A malicious package fixture does not execute an installation script. |
| `REQ-1407` | The installed-profile inventory contains adapters for five ecosystems, and a missing one returns `not_available` with a reason. |
| `REQ-1408` | Analyzer fixtures cover information formats and generalized safe text within resource limits. |
| `REQ-1409` | Timeout, output, and environment checks verify the execution boundary. |
| `REQ-1410` | A privilege-escalation fixture does not pass a password and returns a user action. |
| `REQ-1411` | A removal check deletes only paths in the ownership manifest. |
| `REQ-1412` | An offline check accepts a verified cache and rejects an unknown artifact. |
| `REQ-1413` | After network disconnection, declared offline operations pass and network operations return a typed reason. |
| `REQ-1414` | A detector is declared for every supported harness, and a check rejects detection outside this set. |
| `REQ-1415` | Fixtures cover all four states and always contain a source path and reason. |
| `REQ-1416` | The filesystem snapshot is identical before and after detection, and there is no recursive traversal of the home directory. |
| `REQ-1417` | A two-installation fixture returns both, and the explicit path wins over detected paths. |
| `REQ-1418` | After detection, only the device passport changes; the before-and-after developer-passport snapshots are identical. |
| `REQ-1419` | Windows fixtures cover `.exe`, `.cmd`, npm package metadata, a Scoop manifest, and a Codex WindowsApps package; link, oversized, and invalid metadata are not accepted. |
