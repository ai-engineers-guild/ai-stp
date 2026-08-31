---
description: "Closed vocabulary of required capabilities, its growth rule, and the distinction between unknown and missing capabilities."
last_verified: "2026-08-08"
---

# Capability vocabulary

The requirements owners are `SPEC-005` REQ-511 and `SPEC-006` REQ-601; the passport
field is declared in `component-setup-passports.md`. This document defines the machine
boundary: which `requires_capabilities` values exist, how they are normalized, and what
happens to a value outside the vocabulary.

The vocabulary describes only environment and project requirements. Harness, system,
architecture, license, permissions, and access mode are checked by their own constraints
under `eligibility-constraints.md` and are not expressed as capabilities: each fact has
exactly one validation location.

## Vocabulary entry

```yaml
schema_version: 1
vocabulary_version: "1.0"
capabilities:
  - id: "project.language.python"
    name: "Python"
    description: "The project index contains Python files."
    status: active
```

The `id` field is the canonical value: it is stored in the passport and used for
comparison. `name` is for display and may change without changing `id`. The `status`
field accepts `active` and `deprecated`; a deprecated entry is not offered during
publication, remains valid in already published versions, and continues to be checked.
Deleting an entry is prohibited.

## Normalization

A capability identifier:

- is normalized to Unicode NFC;
- is converted to lowercase;
- consists of dot-separated segments;
- contains from two to four segments;
- permits letters, digits, hyphens, and underscores within a segment;
- neither starts nor ends a segment with a separator and contains no empty segment;
- is no longer than sixty-four characters.

A value that fails normalization is rejected before comparison with the vocabulary.
Invalid form and unknown value are distinct failures with distinct codes.

## Active entries

| Capability | How it is resolved |
|---|---|
| `project.language.python` | the project index contains `python` files |
| `project.language.typescript` | the project index contains `typescript` files |
| `project.language.javascript` | the project index contains `javascript` files |
| `project.language.rust` | the project index contains `rust` files |
| `project.language.go` | the project index contains `go` files |
| `project.language.dart` | the project index contains `dart` files |
| `project.vcs.git` | the project root contains a `.git` directory |
| `project.surface.agents_md` | the project index contains `AGENTS.md` |
| `project.surface.claude_md` | the project index contains `CLAUDE.md` |
| `project.surface.skill_md` | the project index contains `SKILL.md` |
| `project.surface.mcp_json` | the project index contains `.mcp.json` |
| `toolchain.ruff` | the pinned-profile `ruff` tool is installed and current |

## Growth rule

An entry is added only together with an observation that resolves it. A capability whose
value no party can compute does not enter the vocabulary: it would become a failure that
the user cannot remedy and would be externally indistinguishable from an honestly missing
dependency.

This defines the current version boundary: the list describes project and pinned-toolset
facts because those are what the project index and profile installer read. A third-party
tool that the CLI does not observe is not expressed as a requirement—its place is in
the required environment `required_env` or a declared access need.

Adding an entry is compatible and does not require a new passport schema version: the
vocabulary is versioned separately by `vocabulary_version`.

## Unknown and missing

These states are distinct, and the distinction is mandatory:

- **unknown capability** — a value outside the vocabulary. No default is substituted;
  validation returns a typed incompatibility under `SPEC-005` REQ-511. Such a passport
  is invalid and must be corrected by its author.
- **missing capability** — a known value absent from the target. Validation returns an
  incompatibility with that target; the user remedies it by changing the project or
  selecting another target.

The failure names the identifier and, for an unknown value, the nearest permitted
vocabulary entries.

## Distribution

The CLI and API expose the active vocabulary in machine-readable form, so the agent
selects values from the list rather than inventing them. Offline operation uses the last
obtained vocabulary and shows its retrieval time; network absence does not empty the
vocabulary.
