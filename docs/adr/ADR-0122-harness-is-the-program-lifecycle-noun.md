---
description: "Decision to make harness the program-lifecycle noun while leaving toolchain harnesses as a detection read."
last_verified: "2026-08-27"
---

# ADR-0122: `harness` is the program-lifecycle noun

Status: accepted.

## Context

Provider protocol v3 declares three optional operations—`software_install`,
`software_update`, and `software_remove`. As of August 26, six of the seven
released `0.0.4` providers declare them on the wire; `pi` does not and gives
a reason: npm resolves dependencies during installation, so no artifact has a
digest that a plan could pin in advance.

These operations **have no consumer**. In our tree, they exist only as three
members of `Operation` in
`apps/cli/src/ai_stp_cli/provider/protocol_v3.py` and nowhere else. There is
no planner, downloader, applier, or command.

The gap is deeper than a missing command. `_v3_operation`
(`apps/cli/src/ai_stp_cli/commands/install.py`) maps five installation actions
to five primary operations, and no software action appears among them:
requesting one falls into `KeyError` and exits as
`AI_STP_VALIDATION_ERROR: that installation action has no provider v3
operation`. Thus the agent cannot even **ask**—the refusal mechanism
`Capability.require()` exists, but nobody invokes it for software operations.

The word `harness` is already occupied, with a different meaning. The command
registry has `toolchain harnesses`—"which harnesses are supported and which
are present on this machine"—and `toolchain harness-capabilities`—"which
layouts and projections each declares". Both read **detection**: machine state
as it is.

The new capability answers another question: "install the program itself".
That changes state rather than reading it, and its object is different—not the
configuration under `--target`, but the program under `--prefix`.

A released build proves that these two `--` arguments are genuinely distinct:
`plan-operation --operation software_install` without `--prefix` returns a
refusal that states the reason directly.

```json
{"state": "refused", "rejected": true, "reason": "provider_unavailable",
 "detail": "software_install installs a program, which lives under --prefix,
            not under --target; name an absolute --prefix"}
```

A provider planning a program installation without a location would be guessing
a path.

## Options

**Extend `toolchain`.** Put `toolchain install --harness opencode` next to
`toolchain install --tool <id>`. Cheap in code and wrong in meaning: `toolchain
install` installs a pinned tool into a directory we manage
(`<data>/toolchain/tools/<tool>/<version>/`) and **executes nothing from the
archive**. Harness installation places an executable program where the user
specified and unpacks foreign code. One name for two different guarantees is
exactly the second copy of a mistake this repository has already made.

**Name the action inside `install`.** Put
`install apply --action software_install` next to setup installation.
Rejected: `install` belongs to a setup and carries `bundle`,
`setup_stable_id`, and `setup_version`. A program installation has no bundle
or setup, and `expected_target_digest` is deliberately not checked for it—it
has a different subject and different preconditions.

**A new noun, `harness`.** A separate command path, object, and set of
preconditions.

## Decision

`harness` is the program-lifecycle noun. The commands `harness install`,
`harness update`, `harness remove`, and `harness status` manage the harness
program under `--prefix`.

`toolchain harnesses` and `toolchain harness-capabilities` remain detection
reads and change neither name nor meaning.

**There is no third place reporting program state.** `harness status` reports
the installed program; `toolchain harnesses` reports what is visible on the
machine.

A test must guard this, and it appears **together with `harness status`**, not
before. A guard written today would be green because the path it guards does
not yet exist—and a green guard over nothing looks like coverage and stays
green under any future error. This record has already paid that price once and
will not pay it again.

## Consequences

- New duties—the operation journal, backup, and `plan-digest`—are the same as
  for setups; they are reused rather than recreated. **One journal, two action
  maps**—see the amendment below.
- Downloading is ours: `download` is not among the kit's seven commands, and
  both commands that could carry it declare `network_requirement: none`.
  `toolchain.install.download` / `verify` / `remember` / `cached_bytes`
  are reused; unpacking and activation are not implemented at all because the
  provider performs them.
- `_v3_operation` ceases to be the only action map: software actions receive
  their own mapping, and refusal by a provider that does not declare them
  becomes reachable to the agent instead of producing `KeyError`.
- Constraints verified by execution and mandatory for the applier: do not
  replan when `--target` shifts; do not treat a configuration edit as cause
  for repetition; `removed: false` means idempotency, not refusal.
- Rollback: the `harness` commands are isolated; removing them does not affect
  setup installation or detection reads.

## Amendment of 2026-08-26: one journal, two action maps

Implementation exposed a contradiction within this record, and it is corrected
here rather than silently bypassed.

The record says the journal is reused. But `installation.ACTIONS` is a closed
set of five actions, and `installation.propose` validates it itself: reusing
the journal means adding software actions there. Yet the record above says the
opposite—that the setup-installation action map must not know software actions,
or setup installation could accept them.

Both claims are individually true and jointly incompatible.

**Resolution.** There is one journal: the states `planned → approved → applying →
verified`, backup, restoration, and `plan-digest` are identical whether a
configuration or a program is installed. Creating a second state machine for a
different subject would retain two copies of the most expensive part to verify.

There are two action maps. `_v3_operation` remains the **setup installation**
map and continues to reject software actions; `harness` commands have their
own. The separation follows the command surface, not the journal.

**A refusal must name the address.** Today, `_v3_operation` gives `KeyError`
for an unknown action, which exits as "this action has no provider operation"—
the agent sees a failure instead of directions. For software actions, the
refusal names `harness`. This is not a relaxation: `install` still does not
execute them.

The stated cost: `installation.ACTIONS` ceases to list what `install` can do
and becomes the list of what the journal can do. Anyone reading it as the former
will be wrong, so the set gains a comment saying who owns it.

## Amendment of 2026-08-27: `harness status` shipped, with its guard

Three of the four commands had existed since `0.0.5`; `status` remained
declared but nonexistent, along with the guard that this record deliberately
tied to it. Both halves appeared together, as specified here.

**The provider is not queried.** Its `status` describes the **target**, and none
of the kit's seven commands describes a prefix. Asking the program itself for
its version would mean running a foreign executable from a command declared
`read`—exactly what `doctor` declined to do for `gh`.

**Two sources are read, and that is the command's entire point.** The journal
says what this installation did; the filesystem says what is there now. A
status built only from the journal would call an empty prefix successful—and
this is not hypothetical: a provider once unpacked into its sandbox's own
tmpfs, verified the installation where everything was true, and honestly
reported `verified` for files that died with the namespace. The `lost` state
names this case in one word.

Version and entry point are written into `operation_plan` columns during
verification—for the same reason `setup_version` was introduced: the version
also exists in the effect text, but reading it from there means parsing a
sentence written for a human.

**The program-state vocabulary does not overlap the detection vocabulary.**
`toolchain harnesses` already uses `installed` to mean "the product is
visible on this machine". A program under a prefix is a different claim, so its
states have different names: `present`, `removed`, `never_installed`,
`foreign`, `lost`, `interrupted`. A test verifies the disjoint sets rather
than trusting convention; it also verifies that only models in this family
name a prefix—a third place reporting program state would need a prefix to say
which program it meant.

`removed` and `never_installed` are not merged for the same reason
`removed: false` and `verified` are not merged: absence read as removal
provokes a repetition that changes nothing.

## Amendment of 2026-08-27: pi declares what was called absent here

The context above is dated—"as of August 26, providers `0.0.4`"—and was true
at that moment. Today it misleads, so the record remains and the fact is
appended.

Measured on the released `pi-setup-system`:

```text
supported_operations: software_install, software_update, software_remove, launch
```

The reason stated in the context—npm resolves dependencies during installation,
so no artifact has a digest that can be pinned in advance—ceased to apply:
`software.rs` declares exact URLs, byte length, SHA-256, archive form, and
member for Linux, macOS, and Windows. The offline-identity premise is satisfied,
and the shared runtime derives operations from the delivery kind. This does not
change the decision: `harness` remains the program-lifecycle noun. It changes
the claim about who declares it.

The context's second claim—"these operations **have no consumer**"—also no
longer describes the tree. A consumer exists: `harness install`, `update`,
`remove`, `status`, and `resume`. The last was added on August 27 after it
became clear that an operation interrupted after invoking the provider could
only be settled by repeating the entire execution.

This is recorded because the document is read to decide whether the capability
is available. An agent following the context would deny pi an operation that
it declares.

## Review conditions

- If `pi` or another provider begins declaring lifecycle through a mechanism
  with no artifact digest known in advance, the "identity is known offline"
  premise ceases to hold and the entire decision must be reconsidered.
- If providers begin downloading themselves, the consumer role changes and the
  boundaries of this record must be reread.
- If a product appears whose program and configuration live in one directory,
  separating `--prefix` and `--target` will require separate analysis.
