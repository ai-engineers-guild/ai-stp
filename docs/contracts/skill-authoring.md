---
description: "Skill package structure, required and optional fields, and rejection codes."
last_verified: "2026-08-29"
---

# Authoring contract for the `skill` type

The requirements owner is `#455`. The external source is the **Agent Skills Specification**,
<https://agentskills.io/specification>. This document defines the machine boundary: what
is validated, which codes name rejections, and what the validation **is not**.

Of the closed component types, `skill` alone has a specification that exists independently
of this repository. Every limit below therefore comes from that specification rather
than being selected here: a validator whose rules were invented locally can be wrong
only relative to our own opinion.

## Structure

```text
skill-name/
├── SKILL.md          required: frontmatter and instructions
├── scripts/          optional, by convention
├── references/       optional, by convention
├── assets/           optional, by convention
└── …                 any other files and directories
```

`SKILL.md` is located **at the package root**. A `payload/SKILL.md` wrapper makes the
package nonconforming for any reader implementing the standard rather than our layout.

## Frontmatter fields

| Field | Required | Constraint |
|---|---|---|
| `name` | yes | 1–64 characters; lowercase letters, digits, and hyphens; neither starts nor ends with a hyphen; no double hyphens; matches the directory name |
| `description` | yes | 1–1024 characters, nonempty |
| `license` | no | the standard sets no limit, and none is invented here |
| `compatibility` | no | 1–500 characters |
| `metadata` | no | mapping of strings to strings |
| `allowed-tools` | no | space-delimited string; experimental |

A top-level key not defined by the standard is reported as `SK033`. Client-specific
properties belong under `metadata`; this is the standard's own answer.

The body after frontmatter is not validated: the specification says there are no format
constraints, and a validator that adds them imposes taste under the guise of a standard.

## ai_stp extension

`evals/`, `tests/`, and fixtures are permitted and are not rejections: the standard
allows any content in addition to `SKILL.md`. The report lists them separately from
convention directories so the reader can see which belongs to whom.

## Two types under one directory

Under claude-code `skills/`, **two** types exist, distinguished by a manifest rather
than location: `skills/foo/SKILL.md` is a skill; `skills/foo/.claude-plugin/plugin.json`
or `skills/foo/plugin.json` is a plugin. A validator unaware of this calls a valid plugin
a skill without an entry point and sends the author to fix the wrong file.

A vendor-prefixed manifest is matched by the `-plugin` **suffix**, not by a list of
observed vendors: a list makes the fifth vendor a silent miss.

## Codes

| Code | What is wrong |
|---|---|
| `SK001` | this is not a directory |
| `SK002` | `SKILL.md` is not at the package root |
| `SK003` | `SKILL.md` cannot be read |
| `SK004` | frontmatter is absent |
| `SK005` | the frontmatter block is not closed |
| `SK006` | frontmatter is not valid YAML |
| `SK007` | frontmatter is not a mapping |
| `SK010` | `name` is not declared |
| `SK011` | `name` exceeds the limit |
| `SK012` | `name` is outside the permitted character set |
| `SK013` | `name` does not match the directory name |
| `SK020` | `description` is not declared |
| `SK021` | `description` exceeds the limit |
| `SK030` | `compatibility` exceeds the limit |
| `SK031` | `metadata` is not a mapping of strings to strings |
| `SK032` | `allowed-tools` is not a string |
| `SK033` | a top-level field not defined by the standard |

## Command

```bash
ai-stp component skill validate --path <directory> --json
```

Read-only.

## What validation found in our own texts

The validator was run against the eight texts installed by the CLI and found our own
nonconformance: projections carried `harness` as a top-level field, while the standard
defines no such field among its six. It was moved to `metadata`—where the standard itself
directs client-specific properties.

The **installed** form must be validated, not the source tree: the texts reside under
`skills/canonical/` and `skills/projections/`, while `skill install` writes them into the
directory named by its caller. In the source tree, each would produce `SK013`—a name-to-
directory mismatch absent from the installed package. Excluding that code to obtain a
green result would mean not running the validation at all.
