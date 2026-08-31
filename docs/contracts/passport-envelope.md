---
description: "Canonical passport envelope and fact provenance."
last_verified: "2026-08-04"
---

# Passport envelope

A passport is the only machine-readable description of an object. There is no separate "version manifest" entity: immutable-version identity fields are part of its passport under `ADR-0012`.

## Kinds

`kind` has exactly five values:

| `kind` | Object | Mutability |
|---|---|---|
| `developer` | developer | mutable, revisioned |
| `device` | device | mutable, revisioned |
| `project` | project | mutable, revisioned |
| `component` | component version | immutable snapshot |
| `setup` | setup version | immutable snapshot |

Ownership separation among developer, device, and project passports belongs to `ADR-0025`; the closed field set of the device passport is defined in `device-passport.md`.

## Required fields

```json
{
  "schema_version": 1,
  "kind": "developer",
  "stable_id": "developer_...",
  "revision_id": "revision_...",
  "parent_revision_ids": [],
  "owner_id": "account_...",
  "created_at": "2026-08-04T00:00:00.000Z",
  "visibility": "private",
  "facts": {}
}
```

`visibility` describes the object itself and does not replace authorization checks. The developer passport remains private; the public profile is created as a separate projection.

A component-version or setup-version passport additionally contains identity fields: `harness_id`, `version`, tags, exact source and commit, artifact hash and size, provided and required capabilities, `requires_components`, `requires_capabilities`, `required_env`, conflicts, managed paths and native identifiers, permissions and external connection points, license and redistribution capability, and links to verification reports. A component-version passport additionally contains the optional `variant_id`; a setup has no such field under `ADR-0014`.

## Minimal form

One file next to the object combines the passport and version description; its name is fixed in `component-setup-passports.md`. There is no separate duplicate manifest entity. Object identity has the single name `stable_id` in every form under `SPEC-015`; a passport has no `id` field. The common required fields are:

```yaml
schema_version: 1
kind: component
stable_id: component_01JQZK7B8N4M6P2R9T5V0X3Y7Z
name: "pytest-runner"
description: "Runs pytest and parses the report."
version: "1.0"
tags: ["python", "tests"]
source:
  repository: "https://github.com/example/pytest-runner"
  commit: "6f1b0f5f7f3f4f2a1c9d8e7b6a5f4e3d2c1b0a99"
  path: "components/pytest-runner"
```

For a component, `component_type`, `projection_kind`, native implementations, `requires_components`, `requires_capabilities`, `required_env`, permissions, and external connection points are added. For a setup, the purpose, one `harness_id`, and exact component-version references are added.

Arbitrary metadata sets, a generalized evidence graph, and fields "for the future" are not added. An unknown required field and a floating reference are rejected by the schema.

## Fact

```json
{
  "value": "Python 3.12",
  "origin": "observed",
  "confirmation": "user_confirmed",
  "source_refs": ["pyproject.toml"],
  "observed_at": "2026-08-04T00:00:00.000Z",
  "confirmed_at": "2026-08-04T00:05:00.000Z"
}
```

Origin and confirmation are two independent axes under `ADR-0021`.

The `origin` axis has the values `declared` — stated by the user, `observed` — seen by an analyzer, `derived` — computed from other facts by a recorded deterministic rule, and `imported` — transferred from another passport or external source.

The `confirmation` axis has the values `none` and `user_confirmed`. Confirmation does not erase origin. If a repeated observation produces a different value, `confirmation` returns to `none` and the drift is shown to the user; silently carrying confirmation to the new value is prohibited.

The length of `source_refs` is bounded. The optional `confidence` field is allowed for an observation. The `inferred` origin is not used: in practice it is indistinguishable from `observed` with a different confidence and creates false precision. A separate evidence entity and an `evidence_refs` array are not stored in the passport.

The simplification applies only to the environment description. The exact hash, verification reports, signed attestations, and installation plan remain required and immutable.

## Revisions

Changing any fact in a mutable passport creates a new `revision_id` and identifies the parent revisions. Rescanning does not change `stable_id`.

An immutable-version passport is not edited: a correction is released as a new version. Reverification creates a new report and does not rewrite the old result.

## Canonicalization and compatibility

Fields, bytes, and hashes follow `canonical-data.md`. Unknown optional fields are preserved within a compatible major version. An unknown schema major version is rejected with a typed error.
