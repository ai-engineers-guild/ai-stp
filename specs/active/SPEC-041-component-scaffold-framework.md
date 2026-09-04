---
description: "SPEC-041: Versioned scaffold plans for a component's complete authoring catalog."
last_verified: "2026-09-04"
---

# SPEC-041: Component scaffold framework

## Purpose

An author or agent receives a deterministic component scaffold that can be
validated, registered locally, and then enriched with precise provenance for
publication. The same framework also creates a physical setup authoring
directory, distinct from compose and install. Creation is separated from
preview by an exact plan/confirm boundary and never overwrites an existing path.

## Scope

The framework creates a local authoring catalog and a private passport patch. It
does not register the object, invent a public source, license, or authorization,
invoke a package manager, or execute generated code.

## Terms

- **Descriptor** — a private selection of the template/generator version, type,
  language, and harness variant.
- **Scaffold plan** — a content-addressed preview of all files to be created.
- **Scaffold apply** — confirmed creation of a new catalog from the exact plan.

## Requirements

- `REQ-4101`: The descriptor pins the template and generator versions, one of
  the eight component types, the language, a portable or specific harness
  variant, and the executability flag.
- `REQ-4102`: The matrix permits `none` for the declarative `instruction`,
  `skill`, `command`, `agent`, and `setting` types; `mcp` and `plugin` use one of
  the executable languages, while `hook` uses only a language whose source can
  be run after installation without an implicit build. A combination without
  native semantics in the selected harness is rejected before any files are
  written.
- `REQ-4103`: The plan lists every relative path, exact byte length, mode, and
  domain-separated digest and binds them to an absolute new target.
- `REQ-4104`: The current scaffold contains the descriptor as
  `.ai-stp-template.json`, a private component passport patch,
  `SetupEvalProfile`, `.gitignore`, README, and editable source under `source/`.
  A concrete harness additionally receives generated native bytes under
  `projections/<harness>/`; a portable scaffold does not claim a projection.
  The older `/3`, `/4`, and `/5` wrappers remain historical and are not
  regenerated as `/6`.
- `REQ-4105`: The passport patch uses the slug as `name`, omits invented
  descriptions and tags except a skill YAML `description` copied from
  `source/SKILL.md`, uses only `required_env` names, declares empty
  minimal permissions and capabilities, and faithfully retains
  `NOASSERTION`/the prohibition on distribution until the author decides. A
  portable descriptor is not misrepresented as a passport for a specific
  harness. An `instruction` canon is `source/AGENTS.md`.
- `REQ-4106`: Apply rebuilds the plan from the same explicit inputs, requires its
  exact digest, creates owner-only files, rolls back its own
  incomplete result, and fails closed for an existing target, a symlink, or a
  missing parent.
- `REQ-4107`: The eval skeleton contains a local deterministic check, while
  unavailable model/human checks receive `not_run` when executed under
  `SPEC-040`; the scaffold itself does not execute code.
- `REQ-4108`: A concrete scaffold contains a `projections/<harness>/` catalog with the
  exact native layout for the selected harness, marked generated. `instruction`,
  `command`, `agent`, and `setting` receive a native file or catalog from the
  projection registry; an entire settings file is one component. Unsupported
  type/harness pairs are rejected rather than converted implicitly.
- `REQ-4109`: `source/hook-source.json` strictly pins the event, order, blocking
  failure policy, and handler command. The native manifest and adjacent handler
  are derived deterministically; the scaffold does not create a `handle_event`
  stub. A portable scaffold writes those derived bytes under `source/` because
  it has no projection directory; a concrete harness writes them under
  `projections/<harness>/`.
- `REQ-4110`: A manifest-directory plugin carries the selected product's native
  manifest. An OpenCode plugin is a single `plugins/<name>.js|ts` file, while a
  Pi extension is a single JS/TS package entry. Marketplace registration is not
  part of the plugin package and is modeled as a separate `setting`.
- `REQ-4111`: `setup scaffold` creates a physical authoring directory for one
  concrete harness: README, draft `setup.json`, draft `setup-passport.json`,
  eval profile, descriptor, `.gitignore`, optional nested `components/<member>/`
  using the current component wrapper without a nested `.git`, and
  `projections/<harness>/` left empty until export. A portable harness is
  refused.
- `REQ-4112`: Nested `setup.json` members point at
  `components/<name>/projections/<harness>` with `managed_paths` taken from that
  generated native layout, excluding the generated projection note.

## States and errors

A plan is not a persisted mutable object: identical inputs and an available
target produce identical bytes and digest. An invalid matrix combination, stale
plan, modified bytes, or an occupied or unsafe target results in a typed failure
before any user-owned files are modified.

## Security and privacy

The scaffold does not read environment values, credentials, or user files. It
does not access the network or execute created code. The patch contains only an
empty `required_env` list; subsequent enrichment accepts variable names but not
their values. Cleanup removes only files and catalogs created by the current
apply.

## Compatibility and migration

`component-scaffold/6` and `ai-stp/6` are the current independent versions of
the component template and generator; `setup-scaffold/5` and `ai-stp/5` are
current for the setup wrapper. Earlier descriptors remain validatable
against their own schema. A change to the exact generated bytes requires a new
template version; a change to the mechanics without changing the descriptor
contract requires a new generator version. Older descriptors remain validatable
against their own schema.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-4101` | The strict schema rejects unknown fields and values outside the closed vocabularies. |
| `REQ-4102` | A parameterized test covers the entire type × language × variant matrix and negative combinations. |
| `REQ-4103` | A repeated preview matches, and every digest is recomputed from the actual bytes. |
| `REQ-4104` | For every matrix row, the passport and eval profile pass their respective schemas, current wrapper files are present, removed wrapper files are absent, and portable variants contain no generated projection. |
| `REQ-4105` | Fixtures contain no secret values, public source claims, or permission to distribute. |
| `REQ-4106` | Without the exact plan digest, with a stale digest, an existing target, a symlink, or a missing parent, the operation is rejected without modifying files. |
| `REQ-4107` | The eval profile contains deterministic and model-assisted checks; the shared runner confirms an accurate `not_run`. |
| `REQ-4108` | Fixtures for native instruction/command/agent/setting components match the registry; every unsupported pair is rejected without writing files. |
| `REQ-4109` | Hook fixtures preserve the event, order, failure policy, and command; malformed source is rejected by the strict schema. |
| `REQ-4110` | Fixtures distinguish manifest packages from single OpenCode/Pi modules; the plugin does not write marketplace settings. |
| `REQ-4111` | Setup scaffold for a concrete harness writes the wrapper files, nests members without `.git`, and refuses portable. |
| `REQ-4112` | Nested `setup.json` members name the generated projection path and `managed_paths` without the generated projection note. |
