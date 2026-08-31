---
description: "Decision to expand the closed set of supported harnesses from five to seven: opencode remains, cursor and antigravity are added."
last_verified: "2026-08-24"
---

# ADR-0120: The supported harness set has seven members

Status: accepted. Supersedes `ADR-0119`.

## Context

`ADR-0003` and `SPEC-001 REQ-105` declared a closed set of five harnesses, and
`ADR-0119` proposed replacing `opencode` with `cursor`. Both arguments in that
record depended on the estate's state, which changed twice in one day.

First `cursor-setup-system` appeared while `opencode-setup-system` did not
exist—the proposed replacement rested on that fact. Then both
`opencode-setup-system` and `antigravity-setup-system` appeared. Both
reconsideration conditions in `ADR-0119` were met, as recorded in that ADR.

The `NDDev-OpenNetwork` estate has seven setup systems: claude, codex, cursor,
grok, pi, opencode, and antigravity. All are written in Rust, all are public
under AGPL-3, and all vendor `provider-kit/v3` byte for byte:
`kit_version 0.2.0`, `aggregate_digest
sha256:d45add27…`.

This was verified against the API, not a report. The first check showed the
opposite: twenty minutes before confirmation, both new repositories existed
but were empty—`size=0`, with no branch or commit—and one did not exist at all.
"The build passes conformance" and "the repository passes conformance" are
claims about different objects.

## Options

**Keep five and replace one.** The `ADR-0119` decision. Once the opencode
implementation appeared, its first argument no longer held: replacement would
make a working implementation unreachable in favor of one not yet released.

**Keep five without changing membership.** The set stops describing the
estate: two of seven implementations are unreachable by any identifier.

**Expand the set to seven.** The set again describes the estate. The cost is
contract shape: the closed literal, generated schemas, harness catalog,
composition rules, skill projections, and tier table change together, requiring
a new schema version.

## Decision

Seven harnesses are supported: `claude-code`, `codex`, `pi`, `opencode`,
`grok-build`, `cursor`, `antigravity`. Everything outside the set remains
`undefined`.

`cursor` and `antigravity` receive the `beta` tier. Tier membership belongs to
`SPEC-033 REQ-3315` and is updated there.

## Consequences

**The set remains closed.** Expansion does not remove closure: `undefined`
remains the only answer for everything else, and the next membership change
will again require an ADR and a schema version.

**Layouts come from the systems themselves, not product documentation.**
Cursor uses home `~/.cursor` and variable `CURSOR_CONFIG_DIR`; components are
declared by `.cursor-plugin/plugin.json`, so it has no global directories for
skill, agent, command, hook, or mcp, and declaring them would be invention.
Antigravity uses `~/.gemini`, which is not exclusively its own:
`antigravity-cli/` is its own and `config/` is shared with Gemini CLI. The
product documents no variable for relocating the home and documents
instruction and command only at project level. Both facts are recorded in the
catalog as named gaps rather than silence.

**Eight copies of the set are removed.** The harness literal was repeated in
contract models, the command registry, skill projection, local authoring, and
tests. Every copy matched the source exactly until this change. They are now
derived from `HarnessId` and the new `HARNESS_ID_ORDER`, which supplies the same
set in declaration order where a stable list is needed.

**Migration oracles are limited to what they were written for.**
`_MIGRATION_*_ORACLE` values preserve handwritten rules replaced by generation
and prove that generation reproduced them. They assert nothing about a harness
added after migration, so comparison is narrowed to what they cover. Expanding
an oracle would turn a record of what existed into a second declaration of what
exists.

**What this does not provide.** None of the seven is pinned in
`provider-policy.toml` as an Ed25519 `nddev-*-app` release. OpenNetwork
`*-setup-system` repositories have `0.0.1` tags but no signed manifest for our
v2 schema. Policy schema v3 pins linux x86_64 `0.0.1` artifacts in
`attested_releases` and verifies GitHub attestation. Until a digest is in that
list, installation uses `--unverified-provider` and records
`provider_release_trusted: false`. Tier and state are independent under
`REQ-3307`, so `beta` and `not_verified` coexist honestly.

Note dated 2026-08-24: the previous phrase "there are no releases" referred to
our signed manifest and could be read as absence of tags. The tags exist.

## Reconsideration conditions

Reconsider if the estate's size changes again, if an implementation outside
the set appears and the owner decides to support it, or if the owner makes the
set open—in that case a closed literal is no longer the appropriate form and
the decision must be made again.
