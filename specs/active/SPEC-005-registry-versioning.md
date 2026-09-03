---
description: "SPEC-005: Registry, variants, and object versions."
last_verified: "2026-08-24"
---

# SPEC-005: Registry, Variants, and Object Versions

## Purpose

The local and cloud registries unambiguously identify components and setups, retain private drafts, and publish immutable versions for specific harnesses with exact provenance.

## Scope

The scope includes stable identifiers, native component implementations, `X.Y` versions, major-line access, private drafts, tags, visibility, and lifecycle states. Payments, payouts, and modification of published bytes are outside the MVP.

## Terms

- `Component` and `Setup` are stable logical entities.
- `ComponentAdaptation` is the immutable native implementation of one component
  version for one harness.
- `SetupLineage` is an optional provenance relationship between setups for different harnesses.
- `DraftRevision` is mutable private history before freezing.
- `PublishedVersion` is an immutable snapshot with an exact hash.

## Requirements

- `REQ-501`: A component and setup have a stable logical identifier independent of the local path.
- `REQ-502`: A setup belongs to exactly one harness, set at creation and immutable; the native implementation remains a property of the component, not the setup.
- `REQ-503`: A published version has the `X.Y` format and immutable bytes, a version passport, and exact dependency references; no separate manifest entity exists.
- `REQ-504`: A version number cannot be reused for a different hash.
- `REQ-505`: `SetupVersion` pins exact `ComponentVersion` and adaptation references for its one harness; every selected adaptation identity is inside the immutable component version.
- `REQ-506`: Any change to composition, an exact reference, or a materialized overlay automatically creates the setup's next minor version.
- `REQ-507`: Moving to a new major line happens only on an explicit decision — the `--major` flag of `component version release`, never by default — and creates a separate access boundary.
- `REQ-508`: A public component or setup version originates from a public GitHub repository, exact commit, and subpath; a private draft may originate from a hashed local artifact.
- `REQ-509`: An incomplete draft may be synchronized privately but is not registered, ranked, or shown in search.
- `REQ-510`: `component_type` accepts exactly eight values: `instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`.
- `REQ-511`: Dependencies are separated into `requires_components` with exact version references and `requires_capabilities` from a closed, versioned vocabulary.
- `REQ-512`: Native packaging is declared through a separate closed vocabulary, `projection_kind`, and is not mixed with `component_type`.
- `REQ-513`: A version being published has a non-empty tag list, and every tag belongs to a closed, versioned vocabulary; form, normalization, and limits are owned by `docs/contracts/tag-vocabulary.md`.
- `REQ-514`: For each harness in use, a project pins exactly one setup, exactly one selected version, and no more than one installed version; outside the pending-install window they match, and release channels and multiple simultaneously active versions of one setup are not supported.
- `REQ-515`: Relationships between setups for different harnesses are expressed through provenance references and do not create a shared version number, shared immutability, or shared access rights.
- `REQ-516`: There is no product limit on the number of components in a setup; rejection occurs only because of a conflict, incompatibility, or resource limit.
- `REQ-517`: The CLI discovers components in the declared global and project layouts of all seven supported harnesses, installed global GitHub components from supported manifest sources, and MCP server packages from a bounded package manifest and exact entry point; classifies type, native role, harness, and scope; shows path, layout, transport capabilities, and source evidence; and returns a reproducible candidate identifier distinct from the logical Component identifier.
- `REQ-518`: Discovery is separate from acceptance: nothing is imported or registered without an explicit user action, secret values are not read, and the metadata adapter is limited to declared files and size and returns safe diagnostics instead of guessing.
- `REQ-519`: Accepting a component creates a narrow passport in the local registry from an allowlist of observed facts and exact bytes; it does not modify the discovered object and requires no account. Explicit sidecar import, if selected by the user, remains a separate input path.
- `REQ-520`: A repository in which project code and components coexist is supported: the component has its own root distinct from the project root.
- `REQ-521`: Forking an accessible object creates a new stable identifier owned by the recipient and private by default, records provenance, and may synchronize to the recipient's private cloud registry; the original remains unchanged.
- `REQ-522`: An unchanged clone of another party's object is not published under a new namespace; publishing a derived setup requires a substantive change to its composition, passport, or the bytes of an included component, plus full verification.
- `REQ-523`: Publishing a derived component requires changed bytes or passport, plus a new identity and version in the recipient's namespace.
- `REQ-524`: Public derivative publication is permitted only when every included byte and reference is public or belongs to the recipient and the applicable licenses permit redistribution; unknown redistribution rights fail closed.
- `REQ-525`: The owner or their Agent may enrich a local component draft with a private patch against the exact current revision. Each confirmed change creates a content-addressed child revision; a stale revision, secret-bearing field, or unknown field is rejected. Local publication-completeness validation lists every missing and invalid field and does not grant cloud authorization.
- `REQ-526`: The CLI separately parses a published short name, abbreviation, or GitHub URL, a local path, and a collection URL into a bounded source intent without asserting trust. Only separate resolution of a GitHub intent with a full commit SHA creates `github/exact`; a branch, tag, credential-bearing URL, or unsafe subpath does not receive exact provenance.
- `REQ-527`: One executable table owns the identifier, support level, detection root, global and project layouts, projection capabilities, and known gaps for Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor, Antigravity, and the generic `undefined` row; discovery and survey are derived from it.
- `REQ-528`: The CLI creates a safe, portable authoring template for each of the eight component types and deterministically projects it for one specific harness. Conditional blocks are bound to the closed harness registry, the path-placeholder accepts only a bounded relative POSIX path, and unknown or ambiguous syntax is rejected before publication; tags inside fenced code remain literal text.
- `REQ-529`: Within an explicitly named root, the CLI reads `nori.json` and version 3 askill/Vercel-compatible `.agents/.skill-lock.json` in a bounded manner as external metadata ports. Declared components and an exact folder digest become only observed facts of the local draft; repository, commit, trust, and publication readiness are not derived from an external claim. Import executes no script, Git operation, package manager, or network request.
- `REQ-531`: A component version has one logical type and a non-empty set of exact per-harness adaptations under `ADR-0143`; each adaptation binds its harness, implementation mode, source/transform identities and non-empty scope adaptations. Each scope adaptation atomically binds scope, canonical projection format and artifact, provider-native kind, projection kind, exact provider-surface profile/digest/bundle identity, exact supported harness versions and platforms, technical-support declaration and reason, semantic losses, canonical member paths/types/modes/content identities/native IDs, format/parser identity, ownership, write/withdrawal semantics and permissions. The deterministic verifier rejects any digest, size, member, content, metadata or archive-encoding divergence. A provider route or parallel flat lists never synthesize an adaptation.
- `REQ-532`: `origin_harness_id` is optional historical provenance with no effect on eligibility, ordering, verification or recommendation. Adding or changing an adaptation creates a new immutable minor version of the same component.
- `REQ-530`: A layout may declare the key under which a harness stores client-side MCP entries inside a file also declared as a `setting`. Such a file becomes an `mcp` finding only when at least one server is declared, while the `setting` finding is retained. Only server names are read and added to `evidence_refs`; adjacent values are not read. A file with no key, an empty declaration, malformed content, or a size exceeding the limit produces no findings. A harness without a documented layout declares a verified gap instead.

## States and errors

A draft has the states `incomplete`, `valid`, `conflict`, and `frozen`. A published version has the states `active`, `deprecated`, `blocked`, and `hidden`; lifecycle state does not change bytes.

A version in the `deprecated` state remains accessible and installable, while search and status show a warning and an available replacement. A version in the `blocked` state prohibits new installations and updates, but an already installed target is not disabled or removed automatically; the user receives a prominent warning with the reason and a safe next step when these are published. Offline operation uses the last known state and reports its check time.

Regardless of manual state, a version that has lost current mandatory evidence is blocked for new installations and updates under the `SPEC-007` eligibility rule; manual `blocked` remains a separate action layered on top of that rule.

Errors distinguish version reuse, hash mismatch, a missing dependency, invalid provenance, empty tags, and prohibited redistribution.

## Security and privacy

Private bytes are not embedded in a public derived object. License and access rights are checked before materialization. A public artifact contains no local paths, secrets, or unmanaged files. Blocking a version stops new installations regardless of previously granted access.

## Compatibility and migration

Minor versions are available to the owner of the major line; a new major line is not opened automatically. A conflict caused by assigning the same number concurrently on two offline devices is resolved by reissuing under `SPEC-009` REQ-912; a published number never moves. A passport schema change requires a transformation report. An older client reads known fields and preserves unknown optional fields without overwriting the published snapshot.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-501` | A property test moves an object between paths without changing its stable identifier. |
| `REQ-502` | Schema validation rejects a setup without `harness_id`, with multiple values, or with a variant field. |
| `REQ-503` | Mutation tests prove the immutability of published bytes and metadata. |
| `REQ-504` | A uniqueness constraint rejects reuse of `X.Y` with a new hash. |
| `REQ-505` | The golden setup version passport contains exact component references and hashes. |
| `REQ-506` | The change detector proposes the next minor version and prohibits number reuse. |
| `REQ-507` | A release without `--major` never opens a major line; one with it opens the next major line and asks nothing further. |
| `REQ-508` | Publication without a repository, commit, or subpath is rejected; a branch, tag, and `latest` are rejected separately. |
| `REQ-509` | Search and ranking do not see an incomplete cloud draft. |
| `REQ-510` | Enum validation accepts exactly eight values and rejects `marketplace`. |
| `REQ-511` | Schema validation rejects an environment requirement in `requires_components` and vice versa. |
| `REQ-512` | Schema validation rejects a packaging value in `component_type` and a type value in `projection_kind`. |
| `REQ-513` | Publication with empty tags, an out-of-vocabulary value, invalid form, or a limit violation is rejected with distinct errors. |
| `REQ-514` | A project fixture rejects a second setup for the same harness and a second selected version, while the `pending_install` window keeps selected and installed versions separate. |
| `REQ-515` | Changing one setup's version does not change the version or access of a related setup. |
| `REQ-516` | A load fixture for a large setup passes, and rejection occurs only because of a conflict or resource limit. |
| `REQ-526` | A table-driven parser corpus covers every supported form and ambiguous/credentialed/escaping inputs; the resolver accepts only a full SHA and does not elevate local, collection, or published intent. |
| `REQ-527` | Table validation requires eight rows with no duplicate layouts and non-empty sources and projections, compares derived detector/discovery rules with the compatibility oracle, and verifies the complete machine response from `toolchain harness-capabilities`. |
| `REQ-528` | A table-driven test creates a template for each of the eight types and compares repeated projections for seven specific harnesses; unknown, repeated, and nested conditions, an unsafe path, a symlink, and a size violation fail closed, while tags inside fenced code remain literal. |
| `REQ-529` | Fixtures for a Nori skill, subagent, and slash command and for version 3 project/global locks each create one observed candidate and a local draft with an evidence ref and exact folder digest, but without a repository/commit claim; a duplicate key, symlink, oversized content, unsafe path, unknown version, and inexact digest produce safe diagnostics, and the canary script does not run. |
| `REQ-531` | Canonical vectors cover derived and fully native adaptations, whole paths and shared-file contributions; negative vectors reject duplicate harness/scope identities, missing projection bytes, mismatched logical type, ambiguous provider-kind conversion, semantic loss, unsafe paths, incomplete surface identity, incoherent mode/ownership/parser/withdrawal semantics and a route without an adaptation. |
| `REQ-532` | Changing only `origin_harness_id` never changes resolution or ordering, while adding an adaptation requires a new version and cannot mutate the prior version digest. |
| `REQ-530` | Fixtures for `config.toml`, `opencode.json`, and `opencode.jsonc` with declared servers produce an `mcp` finding alongside a `setting` finding and an evidence ref for each name; an empty declaration, missing key, malformed file, and oversized file produce no findings; JSONC comments and trailing commas are parsed; a token-bearing value does not appear in output; the machine-readable table reports a gap for a harness without a documented layout. |
| `REQ-517` | Fixtures for all seven harnesses and the shared `.agents` scope return type, harness, scope, path, and layout-source; Claude GitHub marketplace and Pi Git cache fixtures return exact repository, commit, and package identity, loose/packed refs match, while the npm fixture remains `package/observed` without a remote claim; Python and TypeScript MCP packages require an SDK dependency, declared entry point, and SDK import in the exact source, distinguish stdio/HTTP, and do not classify docs/tests/application hooks; a repeated run returns the same candidate id, and environment overrides lead to relocated roots. |
| `REQ-518` | The registry snapshot does not change after discovery; the secret fixture does not appear in output; a malformed, oversized, or unknown-version manifest, credential URL, and cache escape fail closed with safe diagnostics and no content leakage. |
| `REQ-519` | Offline acceptance creates a narrow allowlist passport and registers exact bytes without an account or modification of the source object. |
| `REQ-520` | A mixed-repository fixture distinguishes the project root from the component root. |
| `REQ-521` | A fork receives a new identifier, recipient owner, and private mode, while the original snapshot remains unchanged. |
| `REQ-522` | Publication of a byte-identical clone is rejected with a typed error, while a derived setup with a substantive change passes only after full verification. |
| `REQ-523` | A derived component without changed bytes or passport is rejected; with changes, it receives a new identity in the recipient's namespace. |
| `REQ-524` | A fixture containing another party's private byte and a fixture with a prohibitive license block public publication of a derived object. |
| `REQ-525` | A process-level scenario passes show/update/validate; a stale expected revision, symlink/oversized patch, secret field, and incomplete exact source produce typed rejections, while a previously released version continues to reference the prior revision. |
