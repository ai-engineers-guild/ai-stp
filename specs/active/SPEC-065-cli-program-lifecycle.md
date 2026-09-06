---
description: "SPEC-065: Shared executable lifecycle for catalog cli components."
last_verified: "2026-09-06"
---

# SPEC-065: Shared cli executable lifecycle

## Purpose

A `cli` component is one executable. Composition must not treat it as a missing
harness namespace, and install/invoke/remove must not copy it into seven
harness homes.

## Scope

Included: composition conversion of `cli`, and `component program install`,
`invoke`, `status`, and `remove`. Excluded: harness program install under
`--prefix`, provider software lifecycle, and seven copies in harness homes.

## Terms

- Shared prefix — the CLI data directory `cli-programs/`, never a harness home.
- Pointer — the selected component version's installed path; never `PATH`.
- Installed identity — exact component ID, version, validated passport and
  artifact bytes at the version's `program` path, not the newest registry row.

## Requirements

- `REQ-6501`: A required `cli` member does not produce `native_surface_lost`.
- `REQ-6502`: Conversion reports `cli` as complete on the shared `bin` surface.
- `REQ-6503`: `component program install`, `invoke`, `status`, and `remove`
  operate on one prefix under the CLI data directory.
- `REQ-6504`: `remove` accepts only a typed component identifier and deletes
  only names under the shared prefix. A path, `..` segment, or linked prefix is
  refused. A component-root symlink is unlinked and a component-root junction is
  removed without deleting its outside target. Recursive removal does not use
  a custom walk that follows nested links.
- `REQ-6505`: Invoke with an explicit version uses that installed version, not
  `current`. Without a version, invoke and status use the version selected by
  the validated `current` pointer. A newer uninstalled registry version must
  not change the reported installed identity. An uninstalled requested version
  is refused without invoking another version.
- `REQ-6506`: Loading verifies stable ID, version, revision hash and canonical
  passport digest against the registry record. Status and invoke compare the
  installed program bytes with the exact recorded artifact and require an
  executable regular file. A pointer cannot escape its component's canonical
  `X.Y/program` coordinate or select a linked version/program path.
- `REQ-6507`: Install refuses pre-existing linked component, version and program
  paths. It replaces program bytes atomically rather than truncating an inode
  that may have another hardlink. Activation uses a unique staging path and
  cannot delete a concurrent install's fixed staging name. POSIX program mode
  is owner read/write/execute.
- `REQ-6508`: A ZIP CLI artifact contains exactly one regular program. Empty,
  ambiguous, linked, unreadable or oversized expanded archives are refused,
  not executed as raw ZIP bytes or selected by first-member order. Raw single
  executable artifacts remain valid. Archive expansion is bounded by the
  local content-store limit.

## States and errors

`AI_STP_VALIDATION_ERROR` — the object is not a `cli` component or the ID is
invalid. `AI_STP_NOT_FOUND` — the version is missing or the requested program
is not installed. `AI_STP_PRECONDITION_FAILED` — remove without `--confirm`.
`AI_STP_CONFLICT` — corrupt identity, tampered bytes, invalid/foreign pointer,
linked destination, ambiguous archive, or failed invocation/install/removal.

## Security and privacy

Invoke never resolves the program through `PATH`; a shebang must name an
absolute interpreter. The environment passed to the process is bounded.
Artifact bytes are already local; the command does not fetch them. The shared
prefix is private to the local installation. These checks do not claim sandbox
isolation against a hostile concurrent process with the same operating-system
account. Process output resource bounds and descendant cleanup require their
own execution controls and qualification.

## Compatibility and migration

`command` remains the slash-command surface. `cli` is a standalone executable
(`ADR-0155`). Existing canonical version/program pointers remain readable;
forged or redirected pointers are refused rather than silently migrated.
No wire generation, new component kind, or sevenfold installation is introduced.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6501` | Composition of a required cli member has no `native_surface_lost`. |
| `REQ-6502` | Convert of a cli member is `complete` with `native_surface=bin`. |
| `REQ-6503` | Install, status, invoke, and remove of one recorded cli artifact. |
| `REQ-6504` | Invalid ID and escaping root-link removal retain outside files; nested link/junction behavior uses the standard library traversal. |
| `REQ-6505` | `test_cli_program_identity.py`: installed `1.0` plus recorded `1.1` still reports `1.0`; explicit uninstalled `1.1` is refused; explicit installed `1.0` does not run current `1.1`. |
| `REQ-6506` | Tampered program bytes and a pointer to another component are rejected by both status and invoke. |
| `REQ-6507` | Component/version/program symlink destinations are refused; replacing a hardlinked program leaves its outside name unchanged. |
| `REQ-6508` | Single-file archive positive control; empty, multi-file, linked and corrupt ZIP negative controls. |

The POSIX shell invocation regression is not a Windows-native executable test.
Release qualification must provide genuine native executable fixtures for each
claimed operating system and architecture.
