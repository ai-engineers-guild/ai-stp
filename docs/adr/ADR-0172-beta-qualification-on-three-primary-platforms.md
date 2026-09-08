---
description: "Beta qualification requires Linux x86_64, Windows x86_64 and macOS arm64; other pairs remain not_verified."
last_verified: "2026-09-08"
---

# ADR-0172: Beta qualification on three primary platforms

Status: accepted

## Context

The owner narrowed the required beta platforms during implementation. All seven
harnesses and four setup postures remain in scope. Linux arm64, Windows arm64
and macOS x86_64 are explicitly not_verified and must not delay this release.
Previously ADR-0160 required six platform pairs for every complete estate record.

## Decision

Estate schema ai-stp-estate-release/2 requires Linux x86_64, Windows x86_64 and
macOS arm64. Required launch coverage is seven providers by these three pairs;
setup/posture coverage is twenty-eight setups by these three pairs. Omitted
required evidence is incomplete. Other pairs are not_verified, not unsupported,
and their absence does not invalidate the selected qualification.

Historical /1 records retain their six-platform interpretation. The schema identity
changes rather than silently relabelling old evidence. Native artifacts may still
be distributed for optional pairs; artifact availability alone is not verification.
Consumer qualification workflows run the three primary pairs. Existing additional
measurements remain historical facts and are not carried forward as current proof.

## Consequences

This supersedes the six-platform requirement in ADR-0160 for new beta records.
Its per-provider launch identity and honest missing/failed-result rules remain.
SPEC-061 and the estate contract define machine acceptance. The same primary set
must drive release evidence, user documentation and support presentation.
