---
description: "Linux x86_64 as the current mandatory release-evidence profile without an unverified macOS support claim."
last_verified: "2026-08-09"
---

# ADR-0062: Linux-first release evidence

Status: accepted.
Clarified by `ADR-0113` regarding how many operating systems are used to prove the CLI surface.

## Context

The early MVP criteria named both Ubuntu and macOS as mandatory. The actual development system, CI, provider isolation, and release rehearsal are built on Linux x86_64. An owned macOS runner has not been activated, and porting the Linux Bubblewrap boundary to Darwin has not been designed. Keeping macOS as a release blocker does not add security to the current product: it either indefinitely blocks a proven Linux release or encourages calling an unperformed verification a success.

The product owner explicitly chose not to consider macOS part of the current implementation and release gate. At the same time, removing all portable code paths would also be incorrect: they are useful for a future separate line and must honestly remain `not_verified`.

## Alternatives

1. Keep Ubuntu and macOS mandatory. Rejected: macOS infrastructure and network-enforcement capability are absent and are not a current priority.
2. Declare macOS supported based on unit fixtures. Rejected: a fixture is not install/provider evidence on a real OS.
3. Make Linux x86_64 the only current release profile and leave macOS as a separate non-blocking portability line. Chosen.

## Decision

The current mandatory profile for the first release is Linux x86_64. The CLI candidate, HarnessBundle oracle, and all five provider lifecycles run on this platform. Claude Code and Codex block the main release with their Linux evidence; Pi, OpenCode, and Grok Build are released and verified using the same secure lifecycle, retaining the beta label under the product contract.

macOS is not included in the current support matrix and does not block issues `#167`, `#170`–`#176`, `#184`, `#185`, or the first MVP release. Until a separate real-host run, it is designated only as `not_verified`; package classifiers, the README, and release metadata must not claim verified macOS support.

The portable code, Darwin refusal, and manual `macos-evidence.yml` are retained as an optional future oracle. The absence of network enforcement on macOS continues to fail closed for an action requiring `network_requirement=none`; this decision does not permit an unsafe fallback or weaken the provider boundary.

## Consequences

- mandatory release records capture the Linux distribution, kernel, architecture, Python, and provider runtime;
- cross-platform deterministic design remains a format invariant, but closing the current task requires literal repeatability on the declared release platform;
- the macOS workflow is not a mandatory check and is not granted release authority;
- adding macOS to the support matrix requires a separate evidence release rather than retroactively changing the existing Linux result.

## Reconsideration Conditions

The decision will be reconsidered when the owner designates macOS as a supported platform, an owned runner becomes available, and the complete wheel/Skill/bundle/provider lifecycle is proven together with an honest network enforcement-or-refusal report.
