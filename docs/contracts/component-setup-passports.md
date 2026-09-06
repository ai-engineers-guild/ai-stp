---
description: "Component and setup version passports, component types, and dependencies."
last_verified: "2026-09-05"
---

# Component and setup passports

A component and a setup each have a stable logical entity and immutable `X.Y` versions. A version is described by its passport under `passport-envelope.md`; no separate manifest exists.

A setup belongs to exactly one harness under `ADR-0014`. A component version
contains explicit native adaptations under `ADR-0143`; a free-standing variant
axis is not part of the first supported alpha contract.

## File next to the object

The passport is stored as one file at the root of the object it describes:

```text
ai-stp.component.yaml
ai-stp.setup.yaml
```

The name is fixed and is a machine boundary: the CLI uses it during discovery to distinguish a described object from an arbitrary directory. The file resides exactly at the object root; a nested companion file defines another object, not part of the outer one. Two files in one root are rejected.

A component root may be located inside a project code repository: under `SPEC-007`, that root, not the repository, is then the publication boundary.

## Local component draft

`component adopt` creates a narrow content-addressed draft in the local registry:
only mechanically observed provenance, native layout, and the address of the exact bytes.
It is not a `ComponentVersionPassport` and does not acquire nonexistent license,
requirements, or capabilities by inference.

Enrichment accepts a closed JSON patch, an exact expected revision, and explicit
confirmation. Every change creates a child revision; a stale patch fails closed.
Patch fields become declared/user-confirmed facts, while observed facts retain their
provenance. Secret-bearing keys, null, unknown fields, unsafe public description text, absolute or
root-escaping managed paths, and an inexact public source are rejected before writing.
The public source repository may be any credential-free HTTPS repository; GitHub is
not a required host.
The patch file has a size limit and is read without following a symbolic link.

Before patching, `component passport suggest` may read only the component's already
stored immutable bytes. Suggestion sources are an explicit closed
`[tool.ai-stp.component]` block in `pyproject.toml`, the equivalent
`ai-stp.component` object in `package.json`, and the complete exact Git provenance
triple recorded during adopt. Each suggested field is returned with a source reference
and `requires_confirmation: true`; the command writes nothing. A missing field remains
in `unresolved_fields`, an unknown or invalid field fails closed, and two manifests
with different values do not get an arbitrarily selected winner. Ordinary package
dependencies do not become component requirements, and the presence of an SDK does
not prove a capability, authorization, or permission.

The `validate --for-publication` profile aggregates all missing and invalid fields and
checks whether a formal `ComponentVersionPassport` can be built with an exact HTTPS
commit and artifact digest/size. Its `ready: true` means only local structural
completeness of the named revision. Cloud publication remains a separate authenticated
plan/apply state machine and is not replaced by local validation.

## Mechanical quality hints

`component passport quality --id <component_id> --json` reads one exact local
revision and returns an optional `mechanical/1` profile. It groups closed checks across
five dimensions: `safety`, `clarity`, `reusability`, `completeness`, `actionability`.
Each check has a stable `code`, a `passed` or `hint` status, related fields, and a
short action for the author.

The profile uses only mechanically available passport facts. For each of the eight
component types, `actionability` checks its appropriate combination of `entry_points`,
`managed_paths`, and `native_ids`; no model, heuristic text assessment, or content
execution is used. `completeness` references the structural publication-readiness
verdict but does not replace it.

The quality report always contains `informational_only=true` and explicit values
`affects_publication_readiness=false`, `affects_component_verified=false`, and
`affects_trust_lane=false`. A `hint` neither blocks release nor proves safety. The
public catalog does not aggregate these local hints without a separate evidence
provenance contract.

## Component types

The list is closed under `ADR-0012`, reduced under `ADR-0015`, and extended
with `cli` under `ADR-0155`:

```text
instruction
skill
mcp
hook
command
agent
plugin
setting
cli
```

Memory, rules, settings, and auxiliary tools are not separate types: they are content
of an `instruction` or `skill`, a `setting` value, or an external toolset dependency.
Changing the list requires a new ADR.

Classification rule, with one example for each type:

| Type | Example object | What makes it this type |
|---|---|---|
| `instruction` | `AGENTS.md` containing repository rules | text in a native instruction format that affects behavior through precedence |
| `skill` | `SKILL.md` containing a review procedure and nested scenarios | a named procedure that the harness attaches as a skill |
| `mcp` | a documentation search server with a declared transport | an external process or address speaking the MCP protocol |
| `hook` | a reaction to an event before writing a file | an executable action bound to an event and matcher |
| `command` | `/review` with arguments and an effect class | a named action explicitly invoked by the user |
| `agent` | a review subagent with its own role and toolset | a declaration of role, model, tools, and delegation |
| `plugin` | a native package contributing commands and hooks together | a native manifest containing other components |
| `setting` | a concurrency-limit value | a typed key-value pair in native configuration |
| `cli` | a `review-kit` executable with a process entry point | a standalone program invoked as a process, not a slash command |

A harness marketplace is not any of these types: it is a delivery channel expressed through `projection_kind`.

## Native packaging

The delivery form is described by a separate closed vocabulary and is not mixed with the component type:

```text
projection_kind: marketplace | plugin | native_files | package
```

The value belongs to provider metadata and the native implementation. A harness marketplace is a delivery channel for other objects, not a component type.

## Component version passport

Contains `stable_id`, `version`, one logical `component_type`, optional
history-only `origin_harness_id`, and a non-empty collection of immutable
adaptations; a nonempty list of tags from `tag-vocabulary.md`; the exact public
source repository, commit and subpath; the component artifact hash and size;
provided capabilities and exact dependencies; required environment variable
names; conflicts; entry points and runtime requirements; external connection
points; license and redistributability; and access mode.

Each adaptation contains a content-derived identity, one harness,
implementation mode (`derived` or `native`), exact common source and transform
identity when derived, and non-empty `scope_adaptations`.

Each scope adaptation atomically binds one scope to its exact projection
artifact, provider-native component kind, projection kind, provider profile ID
and digest, bundle format, permissions, exact supported harness versions,
systems and architectures, immutable technical support and reason, semantic
losses, and canonical members. A member binds path, file/directory type, mode,
exact content artifact for a file, native IDs, content format, parser identity
when structured, whole-path or contribution ownership, write semantics and
withdrawal semantics. These values are not parallel arrays that
can accidentally combine facts from different scopes. Large bytes live in
content-addressed storage; their digest and size are inside the passport.

`ai-stp-adaptation-projection/1` is the sole projection byte format. It is a
ZIP with stored entries in lexical path order, the fixed 1980-01-01 timestamp,
Unix regular-file/directory kinds and declared modes. The verifier checks the
outer artifact digest and size, exact member set, every file content digest and
size, directory emptiness, metadata, and byte-for-byte canonical re-encoding.
Harness versions are exact opaque product-version identifiers, not ranges; an
author lists each tested value and a new value requires a new component version.

`component version release` is the freeze boundary. It refuses an incomplete
draft, builds and verifies the canonical projection, stores those bytes in the
local content-addressed store, normalizes the complete passport, and records an
immutable snapshot without moving or replacing the mutable draft head. A later
publication reads that exact snapshot; it never rebuilds a different passport
from draft facts. Releasing the same unchanged draft as another `X.Y` still
produces a different passport digest because `version` is inside the snapshot.

The first supported form does not contain flat `harness_ids`, a component-level
`harness_id`, `variant_id`, or shared projection/path/native-ID/platform fields.
Earlier alpha bytes remain immutable historical evidence and are not converted
into adaptations by inference.
The `facts.source_links` observation may additionally list safe public source pages,
such as a package's upstream repository and its PyPI, npm, crates.io, Go, or pub.dev
release page. A setup compose manifest may provide one explicit `source_url` for an
embedded component; local-path components receive no invented external link.

## Version description

The sole `description` field belongs to the exact version passport and, for schema
v1, always uses the `commonmark_v1` profile under `SPEC-029` and `ADR-0063`. Raw HTML,
images, and unsafe links are rejected before storage. A card receives only the
deterministic single-line `safe_markdown_v1` excerpt, while detail/preview may receive
safe HTML from the same renderer version. There is no separate object-level or mutable
documentation field; correcting a published description creates a new `X.Y` version.

## Dependencies

Dependencies are separated:

- `requires_components` — exact component version references under `canonical-data.md`;
- `requires_capabilities` — environment and project requirements from a closed vocabulary, such as `project.language.python` or `toolchain.ruff`.

The capability vocabulary belongs to `capability-vocabulary.md` and is versioned by a
separate field. An unknown capability does not substitute a default; it returns a typed
incompatibility. An unknown target value and a missing target value are distinct failures.

## Required environment and access

A component lists only required environment variable names matching
`^[A-Z][A-Z0-9_]*$` and their purpose in `required_env`. A variable's value is not
read, stored in the passport, or passed to the agent. SetupVersion aggregates these
requirements, and the readiness command always reads them from the exact selected
passport: the absence of an additional CLI flag does not hide a requirement. An
additional target-specific name may only extend this list. Readiness commands apply
the same pattern and reject `NAME=value` without echoing the rejected string in machine
output. The environment check returns `set` or `missing` for each name. Installation
and readiness rules for `missing` belong to `SPEC-001` and `SPEC-008`.

The need for access itself is declared separately so the user learns about it before
installation rather than after the first run:

```text
requires_credentials: true | false
requires_authorization: none | user_account | external_service
```

These fields describe whether the object needs credentials and whether a login anywhere
else is required. Neither a key, its value, nor a credential-issuance address belongs
in the passport. The card and search result display this indicator alongside permissions
and external connection points. SetupVersion aggregates the requirement of exact
members, and `install plan` displays it as `required_authorization` before application.

A check that cannot be performed without credentials does not become `passed`: the
author runs it locally with their own credentials, and the CLI issues a signed author
attestation under `validation-policy.md`. A mandatory check without current accepted
evidence blocks public publication. When installing such an object, the agent explains
every required authorization, and launch readiness remains `needs_configuration` until
matching provider-observed `ready` under `ADR-0052` and `SPEC-008`. Missing provider
evidence is not considered readiness.

## Setup version passport

Contains `stable_id`, `version`, and exactly one `harness_id`; a nonempty tag list from
`tag-vocabulary.md`; purpose, target role, and supported tasks; a list of exact component
version references, which may be empty for an explicit complete setup without components;
optional `ported_from` and `related_setup_ids`; the `full-auto` execution profile;
supported harness versions, systems, and architectures; aggregate permissions, required
environment, and external connection points; links to the composition report and
conversion report; links to the artifact, installation check, and launch check; and
access and lifecycle state.

For a locally confirmed version, `artifact` is the canonical
`ai-stp-setup-definition/1`, not a HarnessBundle. It contains exact component refs and
the selection input digest and is hashed in the `ai-stp:artifact:v1` domain. HarnessBundle
includes the passport, so its ZIP digest cannot be included in that passport without a
self-reference; the two identities are not interchangeable under `ADR-0051`.

The `member_metadata_complete` extension field indicates whether every component had a
formal `ComponentVersionPassport` when requirements were aggregated. `false` is allowed
for a private legacy composition but blocks publication and redistribution; it does not
mean that missing metadata is equivalent to empty requirements.

A setup has no `variant_id` field. The relationship between two setups for different
harnesses is expressed through provenance links and creates neither a shared version,
shared version number, nor shared access right.

## Number of components

There is no product limit on the number of components in a setup. Limits arise only
from conflicts, compatibility, and resources.

## Derived components

A small change is stored as a constrained overlay with `derived_from`. Before
installation, the overlay is materialized as a private user version with its own hash,
license, and provenance. Private bytes from another user's component cannot be published
inside the derived object.

## Versions

Changing an exact dependency, content, overlay, or native implementation creates a new
minor setup version. A new major line requires a user decision. A published version
number is never reused.

## Prohibitions

A version passport contains no floating dependencies, local absolute paths, secrets,
environment variable values, arbitrary post-install script, or reference without an
exact hash.
