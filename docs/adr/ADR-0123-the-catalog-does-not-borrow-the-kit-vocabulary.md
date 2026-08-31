---
description: "Decision to rename projection_capabilities to native_authoring so the harness catalog does not look like a closed provider-kit set."
last_verified: "2026-08-26"
---

# ADR-0123: The catalog does not borrow the kit vocabulary

Status: accepted.

## Context

`HarnessDefinition.projection_capabilities` in
`apps/cli/src/ai_stp_cli/local/harness_catalog.py` and `projection_kinds` from
the closed `provider-kit/v3` set share exactly one value and differ in all
others.

The kit set: `marketplace`, `plugin`, `native_files`, `package`.

The catalog declares: `native_files`, `plugin_manifest`, `hooks_directory`.

`plugin_manifest` and `hooks_directory` are absent from the kit set, so these
are clearly different vocabularies. But the shared `native_files` is exactly
enough similarity to make one look like the other. A provider author read it
that way: according to the author, only the missing values stopped them from
editing seven declarations to match a field that the protocol would then have
rejected (`#415`).

Measured against the code rather than its description:

- `projection_capabilities` is read in **exactly one place**—the output of
  `toolchain harness-capabilities`;
- **nothing compares** it with `projection_kinds`;
- `validate_profile_for_projections` compares requested `projection_kinds`
  with the provider profile, and `projection_capabilities` is not part of that
  check.

Therefore, a provider declaring `package` where the catalog names only
`native_files` contradicts nothing today. The danger is not current behavior
but the name: it invites use of the field as a restriction when it is not one.

## Options

**Keep it and add a comment.** Cheap and ineffective: the comment is read by
someone who has already opened the file, while the substitution happens to
someone who saw the name in command output.

**Unify the vocabularies.** Substantively wrong. Catalog values describe which
native forms **our compiler** can write for this harness; the kit set describes
the package family declared by the **provider**. These are different claims
about different parties, and merging them would lose both.

**Rename the catalog field.** Removes the shared `projection` prefix that
causes the substitution without changing behavior.

## Decision

`projection_capabilities` → **`native_authoring`**.

The name was selected after checking that it was unused, because renaming it to
an existing term would reproduce the exact defect this record closes.
`native_surface` is taken and means a relative path within the target;
`native_surfaces` is a key in `local/consent.py`. `native_authoring` did not
appear anywhere in the tree and shares no words with `projection_kinds`.

The field remains what it was: a list of native forms in which a component can
be written for this harness. It does not become a restriction on provider
declarations—if such a check is ever needed, it will be a separate decision
with its own rationale, not a side effect of a name.

## Consequences

- The rename occurs in six places: definition, command, `machine_help` model,
  generated `schemas/v1/cli-harness-capability-table.schema.json`, and two
  tests.
- This changes a machine boundary: the field name is visible in the
  `toolchain harness-capabilities` output read by Skill projections.
- No bundle is at risk: the field participates in no compatibility check.
- Rollback is the reverse rename of the same mechanics.

## Review conditions

- If a real need arises to restrict provider declarations through the catalog,
  that is a separate decision: it will require a mapping between the two
  vocabularies, which does not exist in either direction today.
- If the kit set gains a value matching one of ours, the trap will return under
  another name and must be checked again.
