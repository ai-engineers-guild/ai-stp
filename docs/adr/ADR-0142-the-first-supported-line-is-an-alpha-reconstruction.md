---
description: "Decision to make 0.0.16 the first supported alpha contract without rewriting earlier published evidence."
last_verified: "2026-09-03"
---

# ADR-0142: The First Supported Line Is an Alpha Reconstruction

Status: accepted.

## Context

The repository published `0.0.x` packages, catalog objects and provider
releases while the product contract was still being discovered. Those bytes
and their provenance are real and immutable, but treating every exploratory
shape as a supported compatibility surface would preserve known
contradictions: a flat multi-harness component, one-scope setup operations, an
ambiguous scaffold and a manually fragmented release.

The next consumer version is `0.0.16`. It remains alpha. There is no beta or GA
user contract to migrate, but published artifacts and Git history must not be
rewritten or described as if they never existed.

## Decision

**`0.0.16` starts the first supported alpha line.** Earlier alpha artifacts are
historical evidence, not runtime compatibility obligations. They remain under
their original identities and digests. New readers do not silently reinterpret
or rewrite their bytes.

**The public HTTP namespace remains `/v1`.** Product release numbering, HTTP
namespace and individual machine-schema versions are independent. A changed
canonical form receives an explicit schema and hash-domain identity even while
the user-facing API remains `/v1`.

**The target is one coherent implementation.** Component adaptations,
multi-layer setup transactions, provider wheel trust and release identity are
designed as the first complete contracts. Compatibility shims and dual-write
windows are not product requirements for exploratory alpha shapes. A temporary
bridge may exist only as a bounded migration tool, never as an advertised
supported surface.

**Development remains agent-driven.** Branch protection and mandatory human
review are not release preconditions. Release authorization instead requires
an immutable release plan bound to an exact reachable main commit, required
checks and security verdicts on that SHA, reproducible artifacts, provenance
and a mechanically recomputable estate verdict. History is not rewritten even
though the hosting platform does not enforce that rule.

**Routine publication becomes automatic after trust bootstrap.** Human action
is reserved for creating projects, establishing Trusted Publishers and changing
access. The release controller publishes the six-package dependency closure in
order, verifies already-present bytes before resuming, publishes the CLI last,
creates an immutable GitHub Release and records the deployed web identity.

**The initial recommendation policy is full-auto.** AI STP alone may recommend
the full-auto posture. It means no harness sandbox, permission prompts or
harness-level access questions. It does not grant authority absent from the
runtime environment or bypass compatibility, provenance and safety checks.

**The eight component kinds remain closed and Rust is deferred.** This program
changes how existing components are adapted, transacted and verified. It does
not add kinds or promise a language rewrite by a calendar date.

## Consequences

- Active specifications may replace exploratory shapes directly, but every new
  canonical form still receives explicit identity and reference vectors.
- Production data is not deleted by this decision. A destructive reset remains
  a separate owner decision with backup and recovery evidence.
- Old client/provider mixed-version compatibility is not a release gate for
  `0.0.16`; exact current consumer/provider/estate compatibility is.
- Web deployment is a mandatory estate-verdict row because the public product
  is automatically deployed from this repository.
- `ADR-0048` continues to own separation of build and publication authority;
  its five-package/manual orchestration is superseded here.

## Reconsideration Conditions

Reconsider before beta or GA, when an external user contract requires a
declared compatibility window, or when release authority moves to a controller
with a different exact-identity model.
