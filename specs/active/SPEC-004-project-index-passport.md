---
description: "SPEC-004: Project index and passport."
last_verified: "2026-08-03"
---

# SPEC-004: Project Index and Passport

## Purpose

The CLI deterministically extracts enough structure from the selected project to select and compile a setup. Normal indexing does not send source code to the cloud or turn the MVP into a universal program-analysis system.

## Scope

Level two covers the Git identifier, manifests, lockfiles, versions, frameworks, commands, dependencies, workspace boundaries, agent-facing surfaces, and any bounded safe text file within the root. The limited third level covers symbols and relationships for Python, TypeScript/JavaScript, Rust, Go, and Dart/Flutter. Call graphs, vector representations, and a complete semantic graph are outside the MVP.

## Terms

- `Project` — a stable local identifier for the selected root.
- `discovery root` — a directory within which the CLI performs a bounded search for project candidates and presents them to the user.
- `ProjectPassport` — structured project facts and requirements.
- `ProjectIndex` — bounded level-two and optional level-three data on the device.

## Requirements

- `REQ-401`: The user explicitly selects either the exact project root or a discovery directory within which the CLI presents candidates; the entire home directory is not scanned.
- `REQ-402`: An empty directory, an empty Git repository, or a documentation-only directory is classified as a new project.
- `REQ-403`: Level two extracts manifests, lockfiles, environment and tool versions, frameworks, commands, dependencies, workspace structure, and agent-facing surfaces.
- `REQ-404`: The symbol index is limited to Python, TypeScript/JavaScript, Rust, Go, and Dart/Flutter and returns modules and packages, public symbols, entry points, test files linked to their source, and imports between local modules.
- `REQ-405`: Any bounded safe text file within the root is indexed; structured parsing is applied to known formats, bounded metadata is retained for others, and limits on size, depth, and time are mandatory.
- `REQ-406`: Secret files, binary content, internal version-control-system directories, vendor, cache, and generated-output directories, and paths outside the root are not indexed.
- `REQ-407`: The full index belongs to the local device; the cloud receives only an explicitly allowed passport summary.
- `REQ-408`: Rescanning preserves the stable project identifier and creates a new revision.
- `REQ-409`: A monorepository is one project with one root; packages do not automatically create projects.
- `REQ-410`: A nested Git repository is shown separately and registered only when explicitly selected by the user.
- `REQ-411`: Call graphs, vector representations, private symbol bodies, a global semantic graph, and deep data-flow analysis are not included in the index.
- `REQ-412`: An unsupported language returns `not_available` with a reason, rather than a partial fabricated index.
- `REQ-413`: Within an explicitly selected discovery root, every Git repository is discovered regardless of depth; `.git` directories and `.git` worktree files are treated equally, and resolved aliases do not create duplicates.
- `REQ-414`: Discovery reports exclusions, symlinks, access errors, and reaching the entry limit as closed diagnostics; an access error or limit makes the result `complete=false`, rather than an empty complete response.
- `REQ-415`: Candidates and diagnostics have deterministic order, redacted paths, markers, and a provenance reason; discovery registers nothing.

## States and errors

Scanning distinguishes `new_project`, `indexed`, `partial`, `unsupported_language`, `resource_limited`, and `failed`. The failure of one analyzer does not destroy proven results from other analyzers, but the overall result is not called complete. Cancellation and timeout preserve a partial report without uploading it to the cloud.

## Security and privacy

Paths are normalized before reading. Symlink escape, archive bombs, and excessively large files are blocked. Private source code is not sent to the server during normal indexing. Error messages redact home paths and secret values.

## Compatibility and migration

Each extractor and LSP adapter has a version. A new extractor does not change the meaning of an existing field without a schema version increase. Cache and index invalidation is tied to the source revision, tool version, and configuration hash.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-401` | A negative test proves that neighboring and home paths outside the selected root are not read. |
| `REQ-402` | Empty, Git-only, and documentation-only fixtures receive `new_project`. |
| `REQ-403` | Multi-ecosystem fixtures confirm versions, commands, and agent-facing surfaces. |
| `REQ-404` | Contract fixtures for five ecosystems produce the same result shape for each record kind. |
| `REQ-405` | A mixed extension tree is indexed in full while size, depth, and time limits are enforced. |
| `REQ-406` | Secret, binary, vendor, cache, generated-output, and symlink fixtures are absent from the index. |
| `REQ-407` | A synchronization check transmits only the allowed summary and does not transmit source code. |
| `REQ-408` | Rescanning preserves the project identifier and changes the revision hash. |
| `REQ-409` | A monorepository fixture produces one project and does not create a project for each package. |
| `REQ-410` | A nested-repository fixture is not registered without explicit selection. |
| `REQ-411` | A result-shape check rejects fields for call graphs, vectors, and private symbol bodies. |
| `REQ-412` | An unsupported-language fixture returns `not_available` with a reason. |
| `REQ-413` | A fixture deeper than the former limit contains a regular repository, a worktree, and a nested repository; each appears once with the correct kind. |
| `REQ-414` | Fixtures for excluded, symlink, unreadable, and entry limit show diagnostics; the last two produce `complete=false`. |
| `REQ-415` | Changing the tree creation order does not change machine output; filesystem and registry snapshots match before and after. |
