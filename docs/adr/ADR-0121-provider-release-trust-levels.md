---
description: "Decision to distinguish verified-publisher, signed, build-attested, and unverified provider releases."
last_verified: "2026-08-24"
---

# ADR-0121: Four provider release trust levels

Status: accepted. Extends `ADR-0011`.

## Context

Public setup-system providers are released without a shared privileged key, but
GitHub binds artifact attestations to exact bytes, repository, commit, and
workflow. The existing boolean `provider_release_trusted` does not distinguish
this proof from a signature by an allowed key or from a publisher separately
verified by the platform.

## Decision

A closed level is introduced: `verified_publisher`, `signed`,
`build_attested`, or `unverified`.

`signed` means a verified signature over the exact manifest and bytes by a key
in local policy. `build_attested` means a verified Sigstore/GitHub attestation
of the exact bytes, with the repository, source commit, and signer workflow
specified by local policy. `verified_publisher` is layered on one of these two
proofs and requires the publisher to be pinned in advance as verified in local
policy.

Levels are not additive; the strongest applicable level is selected. A
publisher check mark without verified bytes creates no trust. A manifest,
attestation predicate, remote profile, or downloaded policy does not expand
the local allowlist.

`provider_release_trusted` remains as a compatible derived value: `false`
only for `unverified`. New decisions use the level and its evidence.

## Consequences

- build attestation becomes an independent trust anchor with mandatory binding
  to the exact workflow and commit;
- verified publisher is visible as a stronger level but does not bypass supply
  chain verification;
- the install plan binds the level and evidence, so changing the proof requires
  a new approval;
- old pins for the former estate are removed as superseded; the seven current
  setup systems are allowed only by separate build-attestation rules;
- offline verification requires previously obtained bundles and trusted roots;
  their absence is not considered success.

## Review conditions

Reconsider the decision if the GitHub OIDC/Sigstore identity contract changes,
if a platform-owned release transparency log appears, or if multiple
independent build attestations for one artifact must be compared.
