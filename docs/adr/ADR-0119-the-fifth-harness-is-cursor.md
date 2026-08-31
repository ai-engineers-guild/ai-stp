---
description: "Decision to replace opencode with cursor in the closed set of supported harnesses following the provider estate migration."
last_verified: "2026-08-23"
---

# ADR-0119: The fifth harness is Cursor

Status: superseded by `ADR-0120`.

## Update: both review conditions occurred, and the decision was superseded

The owner adopted the opposite decision: the set expands to seven, `opencode`
remains, and `cursor` and `antigravity` are added. This record is retained as
accepted and superseded—`ADR-0120`. What follows is what was observable when
the review conditions occurred.

Recorded on the day of adoption. The "Review conditions" section below named
two events, and both occurred.

**`opencode-setup-system` appeared.** The factual premise below—"`*-setup-system`
for opencode does not exist in either organization"—ceased to be true. The
repository contains an implementation at commit `f96d206914b2` and vendors the
kit byte for byte: `kit_version 0.2.0`, `aggregate_digest sha256:d45add27…`.
The provider side reports 18/18 against our conformance suite.

**The count changed.** `antigravity-setup-system` also appeared at commit
`66afdb9fa5de`, with the same kit. The estate now has seven setup systems,
while the closed set has five literals.

This was verified against the API rather than accepted from a report, and the
first check produced a different result: twenty minutes earlier both
repositories existed but were empty—`size=0`, with no branches and no
commits—and `antigravity` did not exist at all. The statements "the repository
passes conformance" and "the build passes conformance" refer to different
objects, and that difference was decisive here: the decision was nearly
reconsidered on the basis of a zero-byte repository.

**What this changes.** The first argument for the decision was a factual claim
and no longer holds. The second—the set being closed and equal to the MVP—does
not depend on the existence of implementations and remains intact. But the
property that motivated the replacement was stated as "the set describes the
estate", and after the replacement it would describe five of seven, while one
of the omitted harnesses (opencode) is now available and would become
unreachable after the replacement.

**The decision is neither revoked nor executed.** The replacement was not
rolled out: `HarnessId` still names `opencode`, and neither the corpus nor the
policy was changed. Choosing among "five literals for seven implementations",
"expand the set to seven", and "keep it closed and call this a product
limitation" is an architectural decision owned by the owner. Expanding the
closed set affects `ADR-0003` and `SPEC-001 REQ-105` and requires a new schema
version, so it needs a separate ADR rather than an edit to this one.

## Context

`ADR-0003` and `SPEC-001 REQ-105` declared a closed set of five harnesses:
`claude-code`, `codex`, `pi`, `opencode`, `grok-build`. The set was chosen
for the former provider estate—the five public setup managers that existed at
the time.

The estate moved. Supported implementations are now developed in
`NDDev-OpenNetwork` as `*-setup-system` and are written in Rust rather than
assembled as skeletons. There are exactly five, and the fifth is **cursor**,
not opencode:

| | claude | codex | cursor | grok | pi |
| --- | --- | --- | --- | --- | --- |
| repository | `claude-setup-system` | `codex-setup-system` | `cursor-setup-system` | `grok-setup-system` | `pi-setup-system` |

No `*-setup-system` for opencode exists in either organization. The former
opencode provider remains and is described by its owner as a "setup module
skeleton".

This was verified against the repositories themselves, not their descriptions.
All five vendor `provider-kit/v3` **byte for byte**: `kit_version 0.2.0`,
`aggregate_digest
sha256:d45add27fded30962f411441547c92cc9d06264035c2d314357c24d3d983b819`, and
their `SHA256SUMS` match, file by file, the source that generates this
repository. Their protocol validator is the `provider-v3` crate, which reads
the schema from the vendored kit.

Documented homes taken from their READMEs:

| harness | home | variable | instruction | setting |
| --- | --- | --- | --- | --- |
| claude | `~/.claude` | `CLAUDE_CONFIG_DIR` | `CLAUDE.md` | `settings.json` |
| codex | `~/.codex` | `CODEX_HOME` | `AGENTS.md` | `config.toml` |
| cursor | `~/.cursor` | `CURSOR_CONFIG_DIR` | `AGENTS.md` | `cli-config.json` |
| grok | `~/.grok` | `GROK_HOME` | `AGENTS.md` | `config.toml` |
| pi | `~/.pi/agent` | `PI_CODING_AGENT_DIR` | `AGENTS.md` | `settings.json` |

## Options

**Keep opencode.** This breaks nothing today but diverges from what will be
supported. The set stops describing reality when someone attempts to install
the fifth harness.

**Add cursor as the sixth harness.** This does not require removing existing
content, but the set is declared closed and equal to the MVP: a sixth element
would mean that closure was a formality rather than a property. In addition,
opencode would remain declared without an installable implementation.

**Replace opencode with cursor.** The set remains closed and describes the
estate. The cost is the contract shape: the closed literal, generated schemas,
harness catalog, first-party corpus, and provider trust policy all change
together.

## Decision

The fifth harness is `cursor`. `opencode` leaves the closed set.

The replacement is performed as one change: `HarnessId`, `SUPPORT_TIERS`, the
harness catalog, `_native_path`, first-party corpus, provider policy, skill
projections, `SPEC-008`, and generated schemas. Experience confirms that the
enum and corpus are tightly coupled: changing the literal without replacing
the corpus records fails with `literal_error` during loading—they cannot be
separated.

`cursor` receives the `beta` tier.

## Consequences

**Tier and state remain independent.** Under `SPEC-033`, support tier is a
product decision, while support state answers whether a run has been recorded.
`REQ-3307` explicitly says that the absence of a recorded run is represented
in the state and does not lower the tier. Therefore, `cursor` is declared
supported at `beta` and simultaneously reports `not_verified` until its
release is pinned. This is neither a relaxation nor an advance commitment: it
cannot be installed until the policy pins the bytes.

**The change is blocked by two external preconditions**, both on the
`NDDev-OpenNetwork` side:

- `cursor-setup-system` has no builder content in Cursor-native forms, while
  the first-party corpus is pinned to an exact commit and exact blob trees and
  verified by reconstructing Git identity from the archive—approximation is
  not possible;
- none of the five has any release, while `provider-policy.toml` pins bytes
  and rejects as `release_not_pinned` any release absent from the table.

**The trust policy receives a new line.** The publisher
`NDDev-OpenNetwork`, five `*-setup-system` repositories, five exact digests,
and a signature anchor—the same key or a new one, as decided by the line owner.

**Six opencode artifacts leave the corpus.** Already published versions remain
published: `X.Y` is immutable, and this change does not revoke them.

**`pi` is also corrected.** `_native_path` gives it `agent/AGENTS.md`, while
`agent` is part of the home path, so relative to the target this resolves to
`~/.pi/agent/agent/AGENTS.md`. The harness catalog models the root correctly;
the corpus is wrong. The correction releases new versions of affected
components rather than editing published ones.

## Review conditions

Reconsider if `opencode-setup-system` appears in the supported estate, if the
number of `NDDev-OpenNetwork/*-setup-system` repositories changes, or if the
owner declares the set open—in that case, a closed literal ceases to be the
appropriate shape and the decision must be made again.
