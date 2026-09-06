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
- Installed identity — exact component ID, version, and artifact bytes at the
  version's `program` path, not the newest registry row.

## Requirements

- `REQ-6501`: A required `cli` member does not produce `native_surface_lost`.
- `REQ-6502`: Conversion reports `cli` as complete on the shared `bin` surface.
- `REQ-6503`: `component program install`, `invoke`, `status`, and `remove`
  operate on one prefix under the CLI data directory.
- `REQ-6504`: `remove` accepts only a typed component identifier and deletes
  only names under the shared prefix. A path, `..` segment, or linked prefix is
  refused. A component-root symlink is unlinked without deleting its outside
  target.
- `REQ-6505`: Invoke with an explicit version uses that installed version, not
  `current`. Without a version, invoke and status use the version selected by
  the validated `current` pointer. A newer uninstalled registry version must
  not change the reported installed identity. An uninstalled requested version
  is refused without invoking another version.
- `REQ-6506`: Status and invoke compare installed program bytes with the
  recorded artifact and require an executable regular file. A pointer cannot
  escape its component's `X.Y/program` coordinate or select another
  component's program.
- `REQ-6507`: Install refuses pre-existing linked component, version and
  program paths. It replaces program bytes atomically rather than truncating an
  inode that may have another hardlink.
- `REQ-6508`: A ZIP CLI artifact contains exactly one regular program. Empty,
  ambiguous, linked, unreadable or oversized archives are refused, not executed
  as raw ZIP bytes or selected by first-member order. Raw single executables
  remain valid.

## States and errors

`AI_STP_VALIDATION_ERROR` — the object is not a `cli` component.
`AI_STP_NOT_FOUND` — the version is missing or the program is not installed.
`AI_STP_PRECONDITION_FAILED` — remove without `--confirm`. `AI_STP_CONFLICT`
— the pointer does not name a file or invoke cannot start.

## Security and privacy

Invoke never resolves through `PATH`. The environment passed to the process is
bounded. Artifact bytes are already local; the command does not fetch them.
`--id` is a typed component identifier, not a filesystem path. Remove resolves
the prefix and the named root and refuses a candidate that is not inside the
prefix. A symlink at that name is unlinked without following it.

## Compatibility and migration

`command` remains the slash-command surface. `cli` is a standalone executable
(`ADR-0155`). Historical compositions that treated `cli` as `native_surface_lost`
are corrected; that is not a new component kind.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6501` | Composition of a required cli member has no `native_surface_lost`. |
| `REQ-6502` | Convert of a cli member is `complete` with `native_surface=bin`. |
| `REQ-6503` | Install, status, invoke, and remove of one recorded cli artifact. |
| `REQ-6504` | `component program remove --id ../outside --confirm` raises and leaves the outside directory. A symlink under the prefix to that directory is unlinked; the target remains. |
| `REQ-6505` | Installed `1.0` plus recorded `1.1` still reports `1.0`; explicit uninstalled `1.1` is refused; explicit installed `1.0` does not run current `1.1`. |
| `REQ-6506` | Tampered program bytes and a pointer to another component are rejected by both status and invoke. |
| `REQ-6507` | Component/version/program symlink destinations are refused; replacing a hardlinked program leaves its outside name unchanged. |
| `REQ-6508` | Single-file archive positive control; empty, multi-file, linked and corrupt ZIP negative controls. |
