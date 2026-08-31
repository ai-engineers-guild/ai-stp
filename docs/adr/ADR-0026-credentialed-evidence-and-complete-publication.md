---
description: "Decision to accept signed author evidence for credential-dependent checks and prohibit publication with an incomplete mandatory check."
last_verified: "2026-08-04"
---

# ADR-0026: Author evidence for credential-dependent checks and complete publication

Status: accepted.

## Context

The validation policy contained two incompatible rules. One said that a mandatory check requiring real credentials returns `not_run` and does not block publication. The other required publication to have no mandatory checks in the `not_run` state. `SPEC-007` additionally required the platform to execute the entire mandatory set on the server and prohibited a device report from substituting for anything.

These rules cannot produce a single implementable system. The first allows versions with an incomplete mandatory check into the public catalog. The second, combined with server-side execution, makes publication impossible for any integration that requires user credentials: the platform deliberately does not accept or store third-party keys, so it can never execute such a check itself.

The server-side rule was introduced to protect against excessive trust in device reports and is correct in itself. The mistake was extending it to checks that can legitimately be executed only with the author's credentials.

## Options

1. The platform executes all mandatory checks. Honest for credential-free checks, but credential-dependent objects are either unpublishable or the platform begins accepting third-party keys, which the security model prohibits.
2. A mandatory credential-dependent check remains `not_run` and does not block publication. The catalog fills with public versions whose mandatory checks are incomplete, and the badge and trust line cease to guarantee anything.
3. The author executes credential-dependent checks locally with their own credentials, the CLI issues a signed attestation for the exact hash, the server accepts it according to policy, and the server repeats all credential-free mandatory checks itself. Publication requires a complete set of current accepted evidence.

## Decision

Option 3 is accepted.

**Publication is complete or absent.** Every mandatory blocking check must have current evidence accepted by policy with the result `passed`. A mandatory check in the `failed`, `degraded`, `not_run`, or `expired` state blocks public publication. A completed optional check with a `warning` does not block publication, but the version does not receive `component_verified` and does not enter `authoritative`.

**The accepted evidence source is defined per check.** The server executes a check that can run without credentials, and a device report does not replace it. The author executes a check requiring credentials or external authorization locally with their own credentials through the normal constrained tool path, and the accepted evidence is the author's signed attestation.

**The attestation is bound to exact coordinates.** It is signed by the device key and bound to the object hash, component or setup version, policy version, tool versions, harness and provider version, test case identifiers, result, author account, device, and time. Secret values, tokens, credentials, issuance addresses, and sensitive diagnostics are not included. A change to the hash, policy, tools, or test case set, as well as device revocation, invalidates the attestation.

**The server verifies everything it can.** During publication, the server independently recomputes the hash and structure, repeats credential-free mandatory checks, verifies the attestation signature, binding, and freshness, verifies device and account state, and evaluates policy.

**`component_verified` means evidence completeness, not execution location.** The flag states that every mandatory check for the version has current accepted evidence. The card and machine output show the evidence source and its limitations for every check so that an author attestation cannot be mistaken for platform execution.

**Inability to prove blocks.** If the author cannot obtain a passing credential-dependent attestation, public publication is impossible. Installing such a requirement for a user behaves according to `SPEC-008`: the agent explains every required authorization, installation may complete, and launch readiness remains `needs_configuration` until configuration is complete.

## Consequences

- `docs/contracts/validation-policy.md` receives a single publication barrier, a matrix of accepted evidence sources, and the author attestation record;
- `SPEC-007` changes the requirements for server-side execution and the meaning of `component_verified`, and receives requirements for the barrier and attestation binding;
- `docs/contracts/component-setup-passports.md` stops describing a mandatory `not_run` as publishable;
- `SPEC-008` receives a requirement for explained authorization during installation;
- the card, API, and CLI show the evidence source for every check;
- future scanner integrations and provider evidence must issue compatible attestations for the exact hash.

## Reconsideration conditions

This decision will be reconsidered if a verifiable way appears to execute such checks without the author's credentials, or if signed author attestations become a source of systematic abuse not caught by binding to the hash, policy, and device.
