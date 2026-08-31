---
description: "Decision to compile a component whose landing place is a key inside a provider-owned file as a contribution to that file, reconstructed by the consumer."
last_verified: "2026-08-30"
---

# ADR-0129: A component landing inside another party's file is a contribution to that file

Status: proposed.

## Context

Across seven harnesses, the `mcp` type has three different native forms. The
measurement came from providers `0.0.33` themselves, not product pages:

```text
harness      component_kinds include mcp?   native_namespaces
codex        no                             AGENTS.md, config.toml, hooks.json, prompts, agents
grok-build   no                             AGENTS.md, config.toml, sandbox.toml, skills, …
opencode     no                             AGENTS.md, opencode.json, tui.json, skills, …
cursor       —                              separate owned file mcp.json
antigravity  —                              separate owned file config/mcp_config.json
pi           no such type                   extension package under extensions
claude-code  no                             project .mcp.json, user scope in ~/.claude.json
```

The first three harnesses declare ownership of `config.toml` or
`opencode.json` and **do not** declare the `mcp` type. Their MCP server is a
key inside that file: `mcp_servers` for codex and grok-build, `mcp` for
opencode.

This reveals something previously unexpressed: for three of seven harnesses the
component exists, but no type exists by which it can be given to the provider.
Today they receive `native_surface_lost`—a mechanically correct refusal that is
substantively wrong, because the surface exists inside another party's file.

## Considered options

**Declare the `mcp` type to the provider.** Rejected: the provider does not
declare it, and a consumer-side declaration would assert another party's
contract. The `component_kinds` check would then have to refuse or cease to be
a check.

**Restore `mcp → .mcp.json`.** Rejected: that is the claude-code filename and
was already copied into grok-build (`ADR-0127`). This would repeat the same
error.

**Add key ownership to the protocol.** Rejected: protocol v3 is
bytes-in/bytes-out. A provider that parses TOML to determine whose key it writes
ceases to be what it is and gains a parser for every settings format of every
harness.

**Put only a new `config.toml` in the bundle.** Rejected: that is not assembly
of the full owned projection but overwriting a file with one component's
contents. Everything the component does not know disappears.

## Decision

A layout rule may name a **host file** and a **key** inside it. Such a component
is compiled not into its own surface but into a **contribution** to the host
file's surface.

- The provider receives `replace` for the `setting` surface—a type it
  declares—and all bytes it must write.
- The component passport retains logical type `mcp`. It describes the object,
  not its delivery method.
- The **consumer** builds the full projection: the target's current bytes plus
  this component's keys. This is assembly, not a merge of two setups: the
  “newer” value does not win; declared ownership does—the key belongs to the
  component and everything else remains unchanged.
- The consumer parses the host-file format because it already knows each one:
  `config.toml` is TOML and `opencode.json` is JSON.

Refusal remains where no surface exists in substance. For claude-code,
`.mcp.json` is project-scoped while user scope lives in `~/.claude.json`,
which the provider keeps in `never_touch`; there `native_surface_lost` is
correct and must occur early.

## Where reconstruction happens

Not during bundle assembly. A bundle is portable and has no target; “the
target's current bytes” exist only on the installation machine. One bundle
installed on two machines with different `config.toml` files cannot carry a
premerged file—it would carry someone else's.

Reconstruction therefore belongs to `install plan`, where the target is known
and its current state is read. The bundle carries the contribution—the key and
its content; the full bytes are assembled in the plan and presented for
approval together with the diff.

**Where current bytes come from—and this is not protocol.** The record above
said “the target's current state is read” without saying how. The obvious
interpretation—through the provider—is wrong, and checking took ten minutes
that the next reader should not spend.

Measured: protocol v3 has six main commands—`provider-info`,
`validate-bundle`, `plan-operation`, `apply-operation`,
`recover-operation`, and `status`—and none returns content. `status`
proves `state=managed`, `target_digest`, and drift: a digest, not bytes.

The consumer reads from the filesystem, as it already does:
`local/managed_diff.compare(target: Path, manifest)` walks target roots and
inspects paths. The provider monopoly concerns **writing** final state
(`AGENTS.md`), not reading it. No protocol command is needed; proposing one
would extend another party's contract for something already available here.

This also yields a writing requirement: the writer must preserve formatting.
`config.toml` is maintained by the user, and a round trip through value parsing
and serialization erases every comment. Losing comments in another party's file
is not cosmetic but corruption of data we did not create. Standard-library
`tomllib` only reads; writing values is insufficient.

Dependency closure was checked: `tomlkit`, `tomli_w`, and `toml` are absent;
the project has no TOML writing at all. This is a named dependency with an owner
and removal path in the sense of `AGENTS.md`: it is needed exactly for
format-preserving writing of a host file, is owned by this ADR, and is removed
with the layout rule if that rule is revoked.

## Introduction order

The layout rule is added **last**, not first.

Today's `native_surface_lost` refusal for codex, grok-build, and opencode blocks
installation, which is its job. A rule declaring the surface before
reconstruction exists does not fix refusal; it replaces it with a **silent
skip**: assembly succeeds, installation reports `verified`, and no MCP server
exists on the machine. A visible refusal is strictly better than success that
did not happen.

The order is therefore: read current target state, preserve formatting while
writing, assemble full bytes in the plan, expose a diff—and only then add the
rule after which refusal stops. The reverse exchanges a correct refusal for an
incorrect success.

This is recorded because it was once decided correctly without being written
down: the surface was not declared precisely because reconstruction was absent,
while the reason lived in one test comment.

## Order within one change, not a sequence of changes

The order above describes **what reaches the provider** and was read as a commit
sequence. It cannot be implemented that way, as an attempt—not speculation—
demonstrated: the format writer was written, tested against actual published
`config.toml` and `opencode.json`, and failed two contract gates in this tree.

```text
test_every_module_level_function_has_a_caller
  → "these exist and nothing calls them; wire them in or remove them"
test_no_dependency_arrives_without_a_recorded_reason
  → tomlkit is not in ALLOWED_DEPENDENCIES
```

Both gates are right and say the same thing: a capability does not arrive before
its use. The only lawful caller of reconstruction is the layout rule that this
record says to introduce last. The circle closes.

Hence the clarification that cost one rollback: **the rule is introduced last
within one change.** This means `native_surface_lost` is not removed until
reconstruction works end to end—not that target reading, writing, byte assembly,
and diff arrive in separate commits. They arrive together with the rule and the
dependency whose reason is then recorded.

## Consequences

One type gains three delivery methods, not three types: `provider_kind`
(`#454`) already separates the provider-facing type from the logical type,
while `hosted_in` / `hosted_key` add the third case—landing inside another
party's file.

The rule applies beyond `mcp`. Marketplace registration for claude-code—
`extraKnownMarketplaces` and `enabledPlugins` in `settings.json`—is likewise
a contribution to `setting`, not package extraction (`#458`).

Two components claiming the same entry of the same key conflict rather than
merge, and this must be observed during assembly. No separate code is added:
`native_id_collision` already says one native identifier belongs to one
component, and two servers with the same name under `mcp_servers` fit it
exactly.

Reconstruction must be deterministic: identical input produces identical
bytes, or `plan` and `apply` diverge in formatting and the target appears
changed when it is not.

## Reconsideration conditions

The decision is reconsidered if the provider protocol begins expressing
ownership of a key inside a file; reconstruction then moves to the writing side.
