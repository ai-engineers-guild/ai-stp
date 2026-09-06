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
- Pointer — the exact installed path used for invoke; never `PATH`.

## Requirements

- `REQ-6501`: A required `cli` member does not produce `native_surface_lost`.
- `REQ-6502`: Conversion reports `cli` as complete on the shared `bin` surface.
- `REQ-6503`: `component program install`, `invoke`, `status`, and `remove`
  operate on one prefix under the CLI data directory.
- `REQ-6504`: `remove` accepts only a typed component identifier and deletes
  only names under the shared prefix. A path, `..` segment, or symlink target
  outside the prefix is refused or unlinked at the prefix name; the outside
  target is not deleted.

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
