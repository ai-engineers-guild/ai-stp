---
description: "SPEC-070: Inspect exact setup prerequisites and expose executable preparation steps."
last_verified: "2026-09-07"
---

# SPEC-070: Environment prerequisite inspection

## Purpose

An agent prepares programs, shared tools and access requirements before configuring
one or more harnesses for a project. A successful configuration install alone
does not prove that the surrounding environment can run.

## Scope

Included: read-only inspection of exact local SetupVersions and their exact
components, explicitly selected pinned toolchain tools, managed harness prefixes,
and concrete CLI argument arrays for preparation. Installation remains owned by
SPEC-014, SPEC-067 and the provider software lifecycle; native configuration
coordination belongs to SPEC-069. Inspection does not execute foreign programs.

## Terms

A prerequisite is a program or declared configuration requirement with an exact
source. An observation describes current local evidence. An action is a CLI
argument array; it is never a shell snippet or an automatically executed command.

## Requirements

- `REQ-7001`: Inspection validates exact local setup and component identities and
  digests. Missing or corrupt dependencies refuse; mutable heads are not substitutes.
- `REQ-7002`: Output includes requirements from both setups and components, shared
  executable versions, managed harness observations, environment variable names
  and declared authorization. Environment values and credentials never appear.
- `REQ-7003`: Explicit tool selections resolve to the shipped profile's exact
  version, artifact digest and current platform. Unsupported tools or platforms
  remain blocked, and offline preparation never promises unavailable bytes.
- `REQ-7004`: Shared exact executable versions are inspected separately from the
  current pointer. The agent can invoke the required version explicitly; inspecting
  another version neither changes the pointer nor installs it.
- `REQ-7005`: Actions name actual registry identities and pinned tools. Harness
  installation requires an explicit absolute prefix and target. Missing prefix,
  unknown program version and pending authorization remain explicit gaps.
- `REQ-7006`: Inspection performs no downloads, subprocess execution, registry
  migration or target writes. Repeating it leaves local state unchanged. Program
  availability, prerequisite completion and native configuration verification are
  separate observations; unknown evidence cannot produce an overall ready claim.

## States and errors

Requirement observations are `satisfied`, `action_required`, `not_observed` or
`blocked`. `configuration_state=not_observed` requires subsequent provider-backed
target verification. Existing typed CLI errors cover malformed coordinates and
missing or corrupt local evidence.

## Security and privacy

Inspect environment names only. Neither authentication nor runtime launch is
performed implicitly. Preparation commands retain their own release, digest,
permission, ownership and recovery checks. Returning a setup does not remove
shared programs or other projects' runtime installations.

## Compatibility and migration

This adds a read-only command and exact-version status for shared programs. No
registry migration or portable passport field is added. Runtime needs absent from
passports are not guessed: the agent selects managed tools explicitly after
project inspection. Detection of unmanaged programs is reported separately from
managed installation evidence.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-7001` | Exact local setup resolves; altered or missing component refuses. |
| `REQ-7002` | Component-only access requirements remain visible without values. |
| `REQ-7003` | Pinned installed, absent, offline and unsupported tools have distinct outcomes. |
| `REQ-7004` | Two installed versions report independently; an absent version stays absent. |
| `REQ-7005` | Actions contain selected identities and explicit destinations; missing prefixes remain gaps. |
| `REQ-7006` | Fresh-process inspection preserves registry and target bytes and reports unobserved configuration. |
