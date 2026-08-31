---
description: "Decision to make the projection root a declared bundle fact rather than a call-site assumption, and to recognize shared conventions as a separate installation scope."
last_verified: "2026-08-28"
---

# ADR-0127: A projection surface names the root from which it is resolved

Status: proposed.

## Context

Five projection defects were found in one day, August 27, and all five reduce
to one sentence: **a path is a path only together with what it is relative to.**

```text
grok-build   mcp      .mcp.json       claude-code filename copied from the next line
claude-code  mcp      .mcp.json       project-scope filename labeled global
grok-build   command  commands        the same copied block, third of four
(removal record)                       was itself scope-blind and would take the project row
codex        skill    .agents/skills  correct path, lost root
```

Four of the five look flawless on their own line. None is visible in review;
each becomes visible only when resolving the path or reading the vendor page.

### What the fifth cost

It alone has affected users, and there are many. This was measured by running
published `0.0.7` against released provider `0.0.6` in a clean isolated
`HOME`:

```text
install plan → approve → apply             state: verified
SKILL.md under <target>/.agents/skills      29
SKILL.md under $HOME/.agents/skills          0
```

All 62 components in the codex corpus are skills and declare `managed_paths`
of the form `.agents/skills/<name>`; 61 are published. Against the real target
`~/.codex`, this resolves to `~/.codex/.agents/skills`—a **sibling**
directory, not a nested one.

The provider is honest: it wrote exactly what the plan named. Conformance cannot
see this because its cases are refusals and none asks whether the product reads
what was written. Installation reports `verified`, and the product sees
nothing.

### Why the table could not catch it

`.agents/skills` is not a codex surface. It is a **shared convention**, and the
catalog has long known this: it is declared under harness `undefined` with
`root="home"`, sourced from `learn.chatgpt.com/docs/build-skills`. Moreover,
layout validation explicitly rejects a home binding that names one harness:
`a shared home layout names one harness`.

Thus the catalog knew the answer, while `PROVIDER_RULES`—another table resolved
from `--target`—carries the same row **without any root**. Both tables share
one `Rule` class, whose `root` means something during discovery (`config` is
the product configuration home, `home` is a convention under `$HOME`) and
nothing during projection: the provider owns exactly one directory, the
supplied `--target`.

The defect is therefore not in the row, but in storing the anchor somewhere
other than the path and nowhere at all during projection.

### Facts already checked that eliminate some options

**`--target` is not bound to the product home.** It is required in v3, selected
entirely by the caller, and validated only as an existing absolute directory
(`commands/install.py::_provider_target`). `--target ~/.agents` is already a
valid call without a protocol change. `ADR-0125` records the same fact.

**`undefined` is not a publishable `harness_id`.** `HarnessId` is a closed
`Literal` of seven fixed by `ADR-0120`; it excludes `undefined`. A component
cannot currently be published under a shared convention as a separate
“harness,” and extending the closed set for a non-product would change what a
harness is.

**Nothing in the bundle says from which root `managed_paths` are resolved.**
And—a provider-side correction that changes the fix, not the wording—**the
contract did not claim that either.** v3 never says paths are relative to the
configuration home. The assumption lives in our compiler and in whoever wrote
`managed_paths`: two producers independently made the same habitual
assumption. “The contract assumed incorrectly” and “two producers made the same
assumption” require different fixes: a protocol change versus a declaration
that answers the question.

**One provider build cannot honestly declare both targets.** `provider-info`
publishes one `native_namespaces`, also used by backup, removal, and identity.
`config.toml` means nothing under `~/.agents`, while `skills` under
`~/.codex` means nothing to codex. The question is therefore not which target
to pass, but how the declaration can name more than one scope—the conclusion
both sides reached independently and already underlying `#424`.

## Options

**Leave it as is and fix rows as they are found.** Rejected: five findings in a
day, four invisible in review, and each next finding costs more as published
objects multiply. The fifth already costs 62 immutable versions.

**Forbid shared conventions in projection.** Remove `codex/skill` and declare
that the provider does not install anything outside the product home. Cheap,
but loses a real capability: `.agents/skills` skills are not author error but
a working cross-product convention with a cited source, used by 61 published
objects.

**A provider targeting `$HOME`.** Rejected by the provider side as well:
ownership of the home directory is not ownership but absence of a boundary.
A rollback promise within such boundaries means nothing.

**Let `ai_stp` write the convention itself.** Rejected: only the public
provider writes final harness state, and an exception for an inconvenient
convention destroys the rule on which rollback depends.

**Make the root a declared fact.** Accepted.

## Decision

**The projection root is a declared bundle fact, not a call-site assumption.**

There are three parts. Two do not change the protocol; the third extends an
existing optional list by one allowed value.

**1. A layout names its root, and the root belongs to the vocabulary.** The
catalog already distinguishes `config` and `home`; projection receives the
same distinction explicitly instead of assuming it. A projection rule may not
name a surface bound to `$HOME`: the provider owns only its target, so that
path would resolve beneath the target rather than where the product reads it.

**2. A shared convention is a third scope in `scoped_projection_profiles`, not
a separate harness or build.** `harness_id` remains the product that reads the
component; the closed set of seven does not grow. Today
`scoped_projection_profiles` allows only `target_scope: "project"`; it needs
a third scope, `user_root`, whose root is neither the product home nor the
workspace, and whose surfaces are read as `skills`, not `.agents/skills`,
because the target **is** `.agents`.

Without it, there is no way to declare the profile required by these 62 objects:
one build cannot publish two layouts, while a second build would be an eighth
harness under another name.

Passport consequence: such a component's `managed_paths` are relative to the
convention root—`skills/<name>`, not `.agents/skills/<name>`.

**3. Scope resolution happens once, at the boundary**, as in `ADR-0125`, and
also answers the question absent from the bundle: from which root are
`managed_paths` resolved? This is not a new field but a consequence of the
already selected profile. Downstream there remains one `ProjectionProfile`
and one `--target`.

**4. The shared root is owned per object, not per namespace, and removal under
`user_root` is limited to the provider's own state.**

This became material on August 28: **four** of seven products read
`~/.agents/skills`, not one. This was measured from pinned artifacts: codex
from documentation; grok from its own in-binary reference (the User tier in its
own table); opencode from the vendor page and an in-binary literal; pi from
`package-manager.js:2017`.

It could not be otherwise: `user_root` exists precisely because `~/.agents`
belongs to no single product. Requiring one owner for the root would mean the
convention is used by exactly one harness and thus is not a convention.
Requiring one owner for a namespace inside the root is the same mistake one
level down: `skills` is exactly what is shared.

The rule follows, and it **depends on scope** rather than being universal:

- under `global`, the target is the product's own configuration home, so
  removing a whole namespace is correct—no one else's files live there;
- under `user_root`, whole-namespace removal takes the skills of three other
  products. A provider must remove only what its own state records.

This does not prohibit two providers from declaring the same namespace under
`user_root`: all four will declare it, and that is normal, not a collision.

Separately and outside this rule, `~/.claude/skills` is **not** a conventional
root. It is claude-code global scope, where whole-namespace removal has the
right semantics and `skills` belongs to its provider. Yet three products also
read it (grok lists it as a lower-priority User tier; opencode carries a
literal). The consequence belongs to the consumer, not the provider: installing
a claude-code skill is not an action affecting only one product, and removal
changes what two others see. This is a blast-radius reporting fact, not a reason
to change `global` semantics.

## Consequences

**This requires new versions, not an in-place edit.** `managed_paths` are part
of the content-addressed passport, and published `X.Y` is immutable
(`SPEC-005`). The 62 codex objects receive new versions. This is the same
precedent as pi `managed_paths` in `#408`, and joins a release already carrying
four other reasons: estate migration, `harness_ids` / `supported_os` drift in
115 objects, a `projection_profile_digest` change for cursor, and potentially
stale rendered bytes.

**Five reasons, one release.** Any one alone requires another pass over the same
objects, and every pass means a new `X.Y` for each.

**A guard for the class already exists.** A projection rule may not name a
surface that the catalog binds to `$HOME`; the sole remaining debt,
`codex/skill`, records its object count, cause, and closure condition. The list
shrinks rather than grows: an entry whose rule disappears fails.

**What the decision does not do.** It does not extend the closed harness set,
allow `ai_stp` to write native directories, create a second provider binary,
or require the provider to accept a target it did not declare as its own.

**Its protocol change is explicit:** `target_scope` ceases to have two values.
This extends an existing optional list rather than adding a field or changing
`projection_profile`, so the `ADR-0125` release order remains: CLI accepts the
third value → CLI is released → the provider may declare it. A provider that
does not declare it remains valid for every CLI version.

**The third scope is named `user_root`.**

The provider side correctly required the name to say *where*, not *why*.
`shared`, `convention`, and `portable` describe motives that can age; when a
second convention with a different motive appears, the word becomes wrong
while the enum value is immutable.

`user` was proposed together with an objection: colloquially `global` is also
“user level,” so `user` and `global` read as one axis. The definitions survive
this—`global` means product home—but **this entire day consists of words and
paths that meant two things**, causing all five defects. Adding a value with an
already identified ambiguity to an immutable enum would pay the same cost for
the third time that day.

Therefore `user_root`: only long enough not to read as the `global` axis.
It is the provider side's second option, to which it does not object.

**Schema comment to record.** `user_root` is the only one of the three scopes
whose target cannot be derived: `global` has a documented configuration home,
`project` has the working directory, and `~/.agents` has neither. The caller
must name it. This costs nothing here because every contract command already
takes an explicit `--target`, but it is why the value cannot be inferred and
must be declared.

**Order.** The provider side removes `skill` from its codex declaration in
`0.0.7`; until then installation reports `verified` while writing elsewhere,
afterward it refuses with `unsupported_component_kind`. Refusal is louder than
silence and therefore better, but makes 61 objects visibly rejected on their
tag day. New versions must be ready by then.

## Reconsideration conditions

- If a product reads a shared convention from its own configuration home rather
  than `$HOME`, root separation ceases to be necessary for it and this record
  must be reread.
- If a shared-convention provider cannot be built with the `~/.agents`
  boundary—for example because the convention spreads beyond it—the “forbid
  shared conventions in projection” option returns with its cost of 61 objects.
- If `harness_ids` begins to make one operation install a component for
  multiple products, the “one component, one target” relationship must be
  reconsidered in full.
