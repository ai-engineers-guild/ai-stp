---
description: "Decision to replace flat component harness claims with immutable exact adaptations and separate mutable assessments."
last_verified: "2026-09-03"
---

# ADR-0143: A Component Version Owns Explicit Harness Adaptations

Status: accepted.

## Context

`ComponentVersionPassport` names one `harness_id`, an optional flat
`harness_ids` list, and one shared projection, managed-path set, native-ID set,
permissions object and artifact. That shape cannot say that one logical MCP is a
`config.toml` contribution in Codex, an `mcp.json` file in Cursor and an
extension package in Pi. Provider capability can currently fill the gap by
choosing an available route, but route availability proves what a provider can
write, not that a component contains a correct implementation.

The first supported alpha line begins at `0.0.16` under `ADR-0142`, so the
exploratory flat form is not a compatibility obligation. Its published bytes
and history remain immutable.

## Decision

**One component version contains a non-empty collection of immutable
adaptations.** The component keeps one logical `component_type`. Each adaptation
names exactly one harness and carries the exact native implementation facts for
that harness.

The component may name `origin_harness_id`. It records provenance only and has
no effect on selection order, support, recommendation or verification.

An adaptation contains:

- a content-derived `adaptation_id`;
- one `harness_id`;
- `derived` or `native` implementation mode;
- optional common-source and adaptation-source artifact references;
- an exact projection artifact reference;
- an exact transform identity for a derived implementation and no transform
  for a native implementation;
- logical component type and provider-native component kind;
- projection kind, supported scopes, managed paths and native IDs;
- permissions, supported harness versions, systems and architectures;
- immutable technical support declaration;
- every semantic loss.

**Manifest and bytes have different owners.** The adaptation manifest is part
of the immutable passport and therefore of the version digest. Common source,
adaptation source and generated projection bytes live in content-addressed
storage and are referenced by digest and size. Large bytes are not embedded in
the passport, and no mutable database row can change their meaning.

**Technical support is immutable; verification and recommendation are not.**
The author may declare `unsupported`, `experimental` or `supported`. A separate
AI-STP assessment binds the adaptation to exact harness, provider, platform and
policy identities and reports `not_verified`, `verified`, `stale` or `failed`.
Only AI STP issues a recommendation, and the initial policy has one use case:
`full_auto`. A recommendation is effective only while the assessment is current
and verified and technical support is `supported`.

**Resolution starts from the adaptation.** A provider route is consulted only
after an exact adaptation for the requested harness and scope exists. A route
without an adaptation is `adaptation_unavailable`; it never creates support.
Provider-native kind conversion is allowed only when explicitly named by the
adaptation, the projection preserves the logical function and semantic losses
are empty. Otherwise compilation is blocked.

**The flat form is historical.** `harness_ids`, component-level `harness_id`,
`variant_id`, component-level `projection_kind`, `managed_paths`, `native_ids`
and `supported_os` do not enter the first supported passport form. No reader
synthesizes adaptations from them. Existing content-addressed objects remain
historical evidence and are not selectable for `0.0.16`.

Adding or changing an adaptation creates a new component version. It does not
create a new stable component identity and never mutates a published version.

## Consequences

- Passport, local draft, publication, catalog, selection, sync and persistence
  contracts change together before the new writer is enabled.
- Catalog cards do not gain optional fields that strict clients reject. The
  first supported line receives a versioned detail contract.
- `ComponentVariant` terminology is retired in favor of adaptation.
- Generated projections are reviewable immutable artifacts, not editable
  authoring directories.
- Assessment freshness can change without changing component-version bytes.

## Reconsideration Conditions

Reconsider if a harness publishes a signed universal adaptation format that
preserves all listed semantics, or if the closed component taxonomy changes by
a separate accepted decision.
