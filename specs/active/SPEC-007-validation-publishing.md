---
description: "SPEC-007: Tests, evidence and publication."
last_verified: "2026-09-05"
---

# SPEC-007: Validation, evidence, and publication

## Purpose

The published version is bound to the exact bytes and origin, undergoes mandatory local and server checks, and is not given a stronger status of trust than the evidence supports.

## Scope

Includes hash, structural and security checks, matrix of required checks by object type, device verification, server re-verification, proof of installation, publication plan and explicit confirmation. Absolute security guarantee, arbitrary binaries and post-installation scripts are not included in the MVP.

A complete list of mandatory checks for each type of component, for MVP transport classes and for setup belongs to `docs/contracts/validation-policy.md` and is not repeated here.

## Terms

- `ValidationSnapshot` - results of tools for exact hash.
- `validation policy` — the normative matrix of mandatory checks by object type, owned by `docs/contracts/validation-policy.md`.

Confirmation has two independent axes:

- `author_verified` - platform owners have confirmed the author or namespace;
- `component_verified` — a server policy decision that each mandatory version check has current accepted evidence of `passed`; the source of each item of evidence is shown separately and does not claim execution by the platform.

A confirmed author does not make a version confirmed, and vice versa. Both axes are shown separately and filtered separately.

The proof source accepts exactly five values, and they are not combined into one field `verified`:

- `author_attested` — author’s report signed by the device;
- `platform_digest_verified` - independent server recalculation of the artifact hash;
- `platform_structure_verified` - independent server verification of the scheme and structure without execution;
- `provider_installation_tested` - confirmed installation through the provider;
- `runtime_tested` is a separate proof of the actual launch.

## Requirements

- `REQ-701`: An exact artifact hash is required for every validation and publication state.
- `REQ-702`: Checks distinguish between `passed`, `warning`, `failed`, `degraded` and `not_run`.
- `REQ-703`: The confirmation is signed with the device key and is associated with the account, device, tool versions and hash.
- `REQ-704`: The server rechecks the device state, signature, hash, schema, and non-executable structure rules.
- `REQ-705`: The author's confirmation is not called a platform independent execution or an absolute security verdict.
- `REQ-706`: The public version requires a full passport, a public GitHub repository with the exact commit and subpath, license metadata, non-empty tags and declared harness; branch, tag and `latest` are not the source.
- `REQ-707`: Arbitrary binaries, floating dependencies and post-installation scripts are not allowed by default.
- `REQ-708`: Publishing uses an immutable plan, expiration date, exact hash, and separate user confirmation.
- `REQ-709`: The mandatory set of checks is determined by the check policy matrix by object type and execution class; an unknown type or transport is closed by a refusal, not a pass.
- `REQ-710`: `author_verified` and `component_verified` are stored, displayed, and filtered separately and are not derived from one another.
- `REQ-711`: The verification result stores the source of evidence, tool and policy versions and expiration date; an expired proof is not considered relevant for the line `authoritative`.
- `REQ-712`: Re-publication of other content under an already released version number is rejected.
- `REQ-713`: Publishing a component located inside a repository with project code uses the explicit root of the component and the list of allowed files from its passport, and not the entire repository.
- `REQ-714`: The exact inventory of the artifact files is shown to the user before publishing, and component-root traversals, links, secret-like files, binaries, and undeclared files are rejected.
- `REQ-715`: `author_verified` is issued manually by the platform owners to the account ID or to a confirmed email address and is not derived from any automatic sign.
- `REQ-716`: Issue and revocation of `author_verified` create an audit event with the decision author, reason and time.
- `REQ-717`: Revocation of `author_verified` applies prospectively: it excludes the author's objects from the `authoritative` trust line and does not rewrite historical validation snapshots or already installed targets.
- `REQ-718`: Tags of the published version are checked to ensure they belong to the current dictionary; unknown value and invalid form return different errors, and the response names the nearest valid entries.
- `REQ-719`: When publishing, the platform itself performs each mandatory check that can be performed without credentials on the server, and the device report does not replace it; the accepted source of evidence for each check is given by the matrix `docs/contracts/validation-policy.md`.
- `REQ-720`: `component_verified` means that every mandatory version check has current policy-accepted evidence of `passed`; the attribute is not issued manually, is not derived from authorship, and does not claim that each check was performed by the platform; a version with `warning` is published without verification.
- `REQ-721`: The flag is cleared when the proof becomes `expired` or the new version of the policy introduces a mandatory check that the version does not have; the bytes and historical snapshots do not change.
- `REQ-722`: Hiding, blocking, and restoring a version remain explicit, auditable actions by platform owners—based on their own finding, a private vulnerability report, or a reviewed report case under `SPEC-016`; reports themselves and their number do not automatically change the version lifecycle.
- `REQ-723`: A mandatory check in the `failed`, `degraded`, `not_run`, or `expired` state blocks public publication; a completed `warning`-class check does not block publication.
- `REQ-724`: Mandatory verification that requires credentials or external authorization is performed by the author locally with his credentials, and the accepted proof is a signed author's confirmation tied to the exact hash, object version, policy version, tool, harness and provider versions, test case identifiers, result, account, device and time; secret values, tokens and issuing addresses are not included in it, and changing any binding or revoking the device invalidates it.
- `REQ-725`: Card, API response and CLI machine output show the source of evidence and its limitations for each mandatory check; author acknowledgment is not shown as execution by the platform. The public catalog card projects finished verdicts (`passed` / `failed` / `warning`); optional unfinished checks (`not_run` / `degraded`) remain on the machine audit list and do not enter the card percent.
- `REQ-726`: Suitability for installation is derived from the relevance of mandatory evidence: a version without an up-to-date `passed` loses `component_verified` according to any mandatory verification, leaves `authoritative` and is blocked for new installations and updates; the installed target continues to run with a noticeable warning, no remote shutdown is performed, a new pass through `ValidationSnapshot` of the same bytes restores usability, and the standalone client uses the last known state with the check time.
- `REQ-727`: Before confirmed enrichment, the CLI can only offer fields from the explicit closed block `ai-stp` saved by the immutable manifest or from the full exact source provenance; each sentence names the source, does not write anything down, and does not guess missing, contradictory and irreducible information.
- `REQ-728`: Local optional quality profile applies only deterministic mechanical checks `safety`, `clarity`, `reusability`, `completeness`, `actionability` with type-specific rules for all closed component types; the result is a read-only author hint and explicitly does not affect publication readiness, `component_verified`, or trust line.
- `REQ-729`: The public result of a failed check shows a limited structured summary: number of hits, maximum severity, canonical rule IDs, and safe relative paths. Raw payload, source code lines, scanner stdout/stderr, absolute paths, secret values ​​and arbitrary external tool messages are not published; exceeding the limit is clearly indicated.
- `REQ-730`: The transition of a version to `deprecated` and back is carried out by its author, not staff: obsolescence is a statement about the future of one's own object, and not about its acceptability, and moderation actions are closed `SPEC-026` `REQ-2617`. The basis is the author's explicit action with the reason and `AuditEvent`; the observation about archiving the source (`SPEC-044`) remains a proposal and does not change the state itself. `deprecated` does not limit what is already allowed: the version remains readable, its bytes remain accessible, and it is exactly as published - because the published `X.Y` is immutable, consumers pin the exact versions, and the setup pins its components according to the exact digest. Denying bytes would break every pin already allowed, which is disproportionately more than "don't select this next time." The restrictions are `blocked` and `hidden`. Selection and recommendation sites have the right not to offer an outdated version: this is the meaning of the mark. The transition can be reversed using the same route; The author cannot exit from `blocked` and `hidden`.
- `REQ-731`: In-process safety results are reusable only while a bounded cache TTL and assessment-context fingerprint (scanner versions, policy assets, vulnerability database state, and configured generation) still match; unavailable, transient, degraded, and unfinished evidence is not reusable as a completed assessment. Concurrent requests for one exact subject share one in-flight scan, while different subjects remain independent, and cancellation or failure releases the in-flight entry.

## States and errors

The check statuses are `queued`, `running`, `passed`, `warning`, `failed`, `degraded` and `not_run`. The publication statuses are `draft`, `ready`, `validating`, `publish_planned`, `published`, `deprecated`, `blocked` and `hidden`. The states `blocked` and `hidden` are lifecycle and searchable and do not overwrite the published artifact. The unavailability of a tool does not translate into success. An outdated plan and a changed hash return separate errors requiring a new plan.

## Security and privacy

Checks are run in a limited local environment; the server does not receive source code beyond the published artifact. The platform does not request or store the author's credentials: credential-dependent checks are performed only on the author's device using his own credentials. Tool output is restricted, cleared of secrets, and treated as untrusted. Revoking a device key immediately blocks new confirmations.

## Compatibility and migration

Versions of the validation scheme, tools, and policies are recorded. Re-checking creates a new snapshot without changing the old one. Tightening the mandatory policy does not rewrite the historical result, but may block new installations of the old version.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-701` | The hash mutation check rejects the report and publication. |
| `REQ-702` | Failure and timeout fixtures store `degraded` or `not_run`. |
| `REQ-703` | Signature checks cover live, modified, and revoked device reports. |
| `REQ-704` | Server-side integration check independently recalculates the hash and structure. |
| `REQ-705` | The API and card response template shows separate evidence axes. |
| `REQ-706` | A publication without a passport, repository, commit, subpath, license or tags is rejected, as is a source by branch, tag or `latest`. |
| `REQ-707` | Malicious artifacts block the binary, floating link and script after installation. |
| `REQ-708` | Applying a publication requires a valid plan hash and user confirmation. |
| `REQ-709` | The matrix completeness check maps each object type and execution class to exactly one policy and rejects the unknown value. |
| `REQ-710` | The API response and card template shows both confirmation axes separately and supports separate filters. |
| `REQ-711` | The expired proof fixture excludes the version from `authoritative` without changing the historical snapshot. |
| `REQ-712` | Re-publishing a different hash under the same version number is rejected with a typed error. |
| `REQ-713` | The mixed repository fixture publishes only the declared root component files. |
| `REQ-714` | The inventory is shown before confirmation, and each prohibited file class blocks publication. |
| `REQ-715` | An attempt to obtain author confirmation is automatically rejected; issuance is possible only by the action of the platform owner. |
| `REQ-716` | The audit check records the issue and revocation with the author, reason and time. |
| `REQ-717` | After revocation, the author's objects leave `authoritative`, while historical snapshots and installed targets remain unchanged. |
| `REQ-718` | Fixtures cover unknown tag, invalid shape, and exceeding the limit, and each gives a different error. |
| `REQ-719` | For credential-free verification, substitution of a server result with a device report is rejected, and a forged report is rejected by signature verification. |
| `REQ-720` | The version with `warning` is published and does not receive `component_verified`; manual issuance of a sign is rejected; the version with a full set of accepted evidence, including author's confirmation, receives the sign. |
| `REQ-721` | Expiration of the proof and tightening of the policy remove the sign without changing the bytes and snapshots. |
| `REQ-722` | The multiple complaints fixture does not change the state of the version, but the moderator's action changes it and creates an audit event. |
| `REQ-723` | Mandatory fixtures `failed`, `degraded`, `not_run` and `expired` block publication, but completed `warning` does not block. |
| `REQ-724` | The author's confirmation fixture checks the binding to each coordinate, the absence of secrets and invalidity after changing the hash, policy, tools, test cases and device revocation. |
| `REQ-725` | The card and machine output standard shows the source for each check and distinguishes between server execution and author's confirmation. The card percent and list use finished verdicts; optional unfinished checks remain on the machine audit. |
| `REQ-726` | The expiration, recheck failure, policy tightening, snapshot restore, modified bytes, and offline client fixtures block and restore only new installations without touching the installed target. |
| `REQ-727` | The process fixture receives proposals from the exact artifact, confirms them with a separate update, and proves that there is no writing, no guesswork, no leaking of secrets, and no choice between conflicting manifests. |
| `REQ-728` | A parameterized test builds a profile for each type of component, checks stable codes and type-specific action surface, absence of records and models; an incomplete passport retains publication blockers regardless of `hint`, and machine result contains three obvious negative trust/readiness signs. |
| `REQ-729` | Contract, platform and web tests show rule IDs and relative paths, discard payload, absolute and traversal paths and indicate bounded summary truncation. |
| `REQ-730` | The author translates his own published version into `deprecated` and back with reason and audit; reading the version and loading its artifact continues to respond, but `blocked` and `hidden` do not; from `blocked`/`hidden` the transition fails. |
| `REQ-731` | Platform regressions cover unavailable evidence followed by availability, temporary fetch failure, TTL and generation expiry, valid cache hits, three-way same-subject singleflight, waiter/owner cancellation, scanner failure, cleanup, and different-subject concurrency. |
