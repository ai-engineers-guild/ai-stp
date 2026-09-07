---
description: "Decision to separate reusable artifact safety evidence from target-bound adaptation assessment and derive component verification conservatively."
last_verified: "2026-09-06"
---

# ADR-0163: Assurance is bound to an exact adaptation target

Status: accepted. Supersedes the assessment portion of `ADR-0143` and the
historical `SPEC-059-adaptation-assessments-and-harness-matrix` contract.

## Context

One component version may contain projection artifacts with different bytes,
permissions, provider surfaces, scopes, operating systems, architectures, and
technical limitations. The current version-level safety run identity and
aggregate `component_verified` flag cannot prove which adaptation was checked.
Reusing one successful scan for every adaptation creates false assurance;
rescanning identical bytes without reuse wastes work.

## Decision

Assurance has two layers with different identities.

An **artifact safety observation** answers whether exact immutable bytes passed
a named byte-oriented check under a policy and scanner identity. It is keyed by
artifact digest, check ID, policy version, scanner identity/version, and relevant
execution platform. It may be reused only when every key field is equal.

An **adaptation assessment** answers whether one exact adaptation is acceptable
for one target context. It binds:

- component stable ID, version, and passport digest;
- adaptation ID and harness ID;
- exact scope adaptation and projection artifact digest;
- provider ID, provider version, surface profile ID and digest;
- target scope, harness version range, OS, and architecture;
- assessment policy version;
- the exact artifact observations and compatibility checks used.

Assessment is mutable evidence outside the immutable passport. Its stored state
is `not_verified`, `verified`, `failed`, or `stale`; expiry and policy/profile
replacement affect the effective state without changing component bytes. A
newer assessment supersedes an older assessment for the same full target key but
does not delete history.

Technical support remains the immutable author's declaration. Verification is
the platform's evidence result. Recommendation is a current platform policy
decision derived from technical support, effective assessment, lifecycle,
eligibility, and trust rules. No axis implies another.

`component_verified` remains for compatible clients and is conservative. It is
true only when common component checks pass and every exact adaptation/scope
advertised as installable by the current version has a current verified
assessment for the platform's required target matrix. A failed, stale, or absent
required assessment makes the aggregate false. Detail consumers use the matrix,
not the aggregate, to answer whether a particular target is verified.

The platform persists assessments and projects them. Publication validation is
the platform evidence writer for exact projections present in the version: the
worker scans each unique projection artifact and records one target assessment
per adaptation/scope. The CLI produces additional bounded evidence and consumes
the resulting contract; issue #148 owns that CLI work. Neither an author nor
publication input may issue platform verification or recommendation.

## Consequences

- Mixed states such as Codex verified and Pi failed are representable.
- Identical projection bytes can share a byte scan while retaining separate
  compatibility assessments.
- Refresh and expiry no longer require component re-publication.
- Search and web can filter or display a target state without claiming the whole
  component has that state.
- Existing aggregate verification can become false during migration when its
  old evidence cannot be proven to match the full target key.

## Rejected implications

- A scan of common source is not a scan of every generated projection.
- An adaptation ID alone is insufficient because provider profile and target
  platform change compatibility.
- A passing assessment does not grant install authority or ownership.
- Missing evidence is `not_verified`, never inferred from another target.

## Revisit conditions

Revisit if all providers adopt one cryptographically identical target surface,
or if policy defines a smaller explicit required-target matrix for aggregate
component verification.
