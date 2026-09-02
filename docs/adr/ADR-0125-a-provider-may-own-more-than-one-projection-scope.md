---
description: "Decision to allow a provider to declare a projection for project scope in a separate optional list without changing the existing profile or its digest."
last_verified: "2026-09-01"
---

# ADR-0125: A provider may own more than one projection scope

Status: accepted.

## Context

`#424` and `#425` cannot be closed because Antigravity documents commands and
instructions at workspace scope, under `.agents/`, while the provider owns only
the global home `~/.gemini`. The provider refuses to declare `command` and
`instruction`, and that refusal is correct: a declared type is a rollback
promise, and there is no route for it.

Three facts were measured before the decision.

**`--target` is not bound to the product home.** It is injected by the invoker
(`provider/invocation_v3.py`), is required for every command, and names the
directory selected by the caller. `--target <project>` is already a valid call
today. The protocol prohibits nothing here.

**The only command that does not receive `--target` is `provider-info`.** It
describes a **release**, not a target. Therefore its singular
`projection_profile` is not an oversight: the declaration has no target against
which one of two profiles could be selected.

**Our own catalog already asserts two scopes.** `local/harness_catalog.py`
describes layout with the `Layout` type, which has a `scope` field with values
`global` and `project` (`G` and `P`, lines 100-101). `opencode` is declared
in both: the same component types with and without the `.opencode/` prefix.
`codex` declares `hooks.json` only in project scope.

This yields the fact that resolves the question: **one harness already owns two
scopes** on our side. The provider declaration, not the catalog, is behind.

## Release order that must not be rearranged

`parse_capabilities` compares the field set for **exact equality**:

```python
required = frozenset(INFO_FIELDS)
if frozenset(value) != required:
    raise ValueError("provider-info fields differ from the closed v3 schema")
```

The same happens below for the profile itself. Therefore a provider that adds a
field is rejected **in full**: this is not merely an unrecognized profile;
`provider-info` does not parse, making `fetch`, `conformance`, `plan`,
`apply`, and `status` unavailable with it. To a user on an already installed
CLI, such a release looks like a completely broken provider, and the message
refers to the schema rather than the scope.

An old CLI cannot be made tolerant retroactively. Therefore:

```text
1. CLI accepts the new field
2. CLI is released
3. only then may the provider declare it
```

The reverse order breaks everyone who has not upgraded, and a provider release
cannot fix it.

## Options

**An eighth `harness_id` for project scope.** A new binary, a new identity, and
zero protocol changes. Rejected: this would contradict what the catalog already
says about the seventh product. Antigravity in a project and Antigravity in
`~/.gemini` are one product with two scopes in exactly the sense in which
`opencode` already is. The set would not grow; it would become inconsistent
with itself.

**Namespaces valid in both scopes.** Rejected: one name would mean different
paths depending on the supplied target, and `provider-info` would cease to be a
verifiable assertion.

**Change the shape of `projection_profile` by adding scope inside it.** Rejected
for a reason more important than preference: the profile `digest` binds the
exact declaration through `digest_canonical(PROJECTION_DOMAIN, digest_input)`.
Any new field inside changes the digest of **every existing** profile and thus
causes `projection_profile_mismatch` for every bundle built against the old
profile. That is exactly the cost for which `#415` asked us not to alter
declarations speculatively.

**An optional adjacent list.** Accepted.

## Decision

`provider-info` receives an optional `scoped_projection_profiles` field: a
list of profiles, each of which **names its own scope**.

`projection_profile` does not change at all, not by a single field. It remains
the declaration of global scope, and its digest remains byte-for-byte unchanged.
A provider that does not declare a second scope is valid for every CLI version,
including installed versions.

Rules that make the list a verifiable assertion rather than free-form text:

- the scope comes from the catalog's existing vocabulary: `global` and
  `project`. This record introduces no new values;
- an entry with the value `global` is **rejected**: global scope is already
  described by `projection_profile`, and two assertions about one fact are a
  defect even while they agree;
- scope is unique within the list;
- each entry carries its own `digest`, binding its own declaration, including
  the scope;
- absence of the field means that the provider owns only global scope. This is
  neither degradation nor a warning.

**Resolution happens once, at the boundary.** The target is known by planning;
its scope is determined by matching catalog layouts, not by guessing. Downstream
there is still **one** `ProjectionProfile`.

The plan artifact does not change. It already contains
`projection_profile_digest` and simply begins carrying the digest of the
resolved profile; status is checked against the same value. A provider that
echoes the global digest where the plan resolved the project digest is caught by
the existing check, without a new one.

## Consequences

- The eleven places that read `capabilities.projection` **do not change**: all
  take one profile. The declaration, not application, becomes multiple.
- `PROVIDER_RULES` in `local/composition.py` must learn the scope: its key is
  `(component_type, harness_id)`, and the same component type in different
  scopes lives at different relative paths. This debt already existed: the table
  duplicates `Layout`, which has scope, and the poorer of the two records is
  being read. The correct separation is to derive `PROVIDER_RULES` from the
  catalog rather than add a third key to it.
- A refusal must name the scope. “The provider does not declare `command`” and
  “The provider does not declare a projection for a project target” are
  different causes, and the first sends the reader in the wrong direction.
- A provider may not declare a component type in a scope for which it lacks
  transactional install, status, and restore. A declared type is a rollback
  promise.
- The cost, stated explicitly: `provider-info` ceases to be a flat declaration.
  A release may now have multiple ownerships, and the question “what does this
  provider own?” no longer has an answer without specifying the target.

## Amendment of 2026-08-26: `PROVIDER_RULES` cannot be derived from the catalog

The record above says that `PROVIDER_RULES` duplicates `Layout` and that the
correct separation is to derive the former from the latter. An attempt to do so
disproved the assertion, and it is corrected here rather than left for the next
person to trust what was written.

**The tables answer different questions.** `PROVIDER_RULES` answers “where does
the provider write a component of this type?” `Layout` answers “where might a
person have written it?”—and the catalog is **intentionally incomplete**, as its
own comment states: importing only what is declared would silently lose foreign
configuration. Therefore the absence of a catalog row is not evidence against a
rule, and deriving from an incomplete table would yield an incomplete projection.

Measured: the tables differ in thirteen places. In twelve, one table knows a
surface about which the other is silent, and all twelve fail closed. Not one of
the **fifteen** harness-and-type combinations actually published in the live
catalog was left without a projection route.

The thirteenth was a contradiction: `grok-build` / `mcp`, where the rule named
`.mcp.json` against the catalog's sourced `config.toml`. It alone did not fail
closed and was fixed separately.

**What remains true and verifiable.** Where both tables name the same type for
the same harness in global scope, they must agree. This is the sole shared entry
that once diverged, and a test guards it. The test does not depend on either
table being complete.

Consequence for projection scope: `PROVIDER_RULES` must learn scope **itself**
rather than inherit it through derivation. This costs more than stated above,
and it is better to know that before work begins. Measurement details are in
`#432`.

## Reconsideration conditions

- If a harness with a third scope—not `global` or `project`—appears, the
  vocabulary must be extended, and it must be extended in the catalog where it
  lives, not here.
- If `provider-info` ever starts receiving `--target`, this entire list
  becomes unnecessary: the declaration can answer directly for the named target,
  and a singular value will become honest again.
- If two profiles of one provider begin to overlap in managed paths, the
  assumption of non-overlapping ownership will cease to hold, and scope
  separation will require separate analysis.

## Amendment of 2026-09-02: the consumer chooses the scope per plan

The provider half landed a release at a time; the consumer half did not exist:
`rule_for` answered by kind and harness alone, the catalog recorded a
component's discovery scope that nothing read, and every install compiled for
the harness home. Antigravity has declared a `project` profile since `0.0.53`
and cursor since `0.0.54`, so the missing half was ours.

The scope is a **choice made per bundle and per plan**, not a property read off
the components: `select bundle --scope` and `install plan --scope` take
`global` (default) or `project`, a `project` plan requires an explicit
`--target` naming the workspace, and the compiled bundle records a non-default
scope in its manifest. A rule file adopted from one repository is content;
where it lands next is a decision, and defaulting that decision from where the
file was found would install a project's rules into a home because they were
discovered there. Rules exist per kind, harness and scope; a kind the provider
declares at no such scope is `unsupported` at that scope rather than routed to
the home surface of the same kind. `user_root` stays a member of the home
family: it is the provider's arrangement of one home surface (`ADR-0127`),
not a second place to install. Owned by `SPEC-006` `REQ-632`.
