---
description: "Historical audit dispositions reconciled with current mechanism owners."
last_verified: "2026-09-07"
---

# Historical audit dispositions

This document retains the disposition of the August 2026 RVR audit. Its issue
numbers refer to the historical source repository and must not be interpreted as
current public issues with the same numbers. The current execution plan belongs
to [implementation-roadmap.md](implementation-roadmap.md); CI and deployment
mechanisms belong to [ci-cd.md](../operations/ci-cd.md). This record does not create
a second release checklist or new authority requirements.

`confirmed` means the original defect was reproduced; `modified` means later
implementation changed the applicable boundary. Neither disposition alone means
that a later release candidate has been exercised.

## Disposition matrix

| Historical finding | Disposition | Current mechanism | Evidence owner |
|---|---|---|---|
| `RVR-P1-001` | `confirmed` | Shared CI/deploy trust domain. Public CI uses GitHub-hosted runners. The host independently pulls the promoted public ref; it is not an Actions runner. Candidate build and attestation retain separate privileges. The former fleet/host-runner description is superseded by `ADR-0103` and `ADR-0109`. | Owner: repository operations. Preserve workflow/host separation checks and verify every promoted deployment. |
| `RVR-P2-002` | `confirmed` | Cancellation during deployment. Check cancellation is separate from serialized promotion and host-side locking/recovery. The current workflow and deploy fault tests own the behavior. A dedicated staging tier is not introduced. | Owner: repository operations. Preserve workflow/host separation checks and verify every promoted deployment. |
| `RVR-P2-003` | `confirmed` | Deployment SSH credential. The public workflow holds no host credential. The host fetches anonymous HTTPS. The old instruction to wait for a first deployment before removing obsolete secrets is historical, not a current prerequisite. | Owner: repository operations. Preserve workflow/host separation checks and verify every promoted deployment. |
| `RVR-P2-004` | `confirmed` | External health proof. `verify-public` observes public DNS/TLS and served commit/environment/schema from GitHub-hosted execution. Current deployments have reached and passed this job; each new promotion still needs its own result. | Owner: repository operations. Preserve workflow/host separation checks and verify every promoted deployment. |
| `RVR-P2-005` | `modified` | Wrong branch or source SHA. Promotion checks successful push-to-main provenance and exact checked SHA. Branch protection remains governed by `ADR-0115`; historical issue `#188` is not an active requirement here. | Owner: repository operations. Preserve workflow/host separation checks and verify every promoted deployment. |
| `RVR-P2-006` | `confirmed` | Unmerged server contract. The server implementation is in the public product. Current regressions and specification acceptance replace an obsolete transfer plan through a removed `dev` branch. | Owner: platform. Preserve current server regressions; no transfer remains. |
| `RVR-P2-007` | `confirmed` | Artifact transport. Public exact-version reads verify stored bytes. Current private owner/grantee closure is tracked separately in the roadmap; public-route existence does not prove private access. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `#180` | `modified` | Two-device sync. Durable cursor/journal and merge have repository tests and an executable account-bound evidence slice. Run the current slice with genuine device login on the candidate being qualified. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `#170/#171` | `modified` | Provider lifecycle. Provider scope is the canonical seven-harness registry. Current acquisition and conformance evidence use exact public release artifacts, not the retired two-provider estate. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `RVR-P2-008` | `modified` | MacOS coverage. The former Linux-only release statement is superseded. Current native OS/architecture qualification belongs to the release-evidence owner and G5; classifiers or a Linux run cannot supply missing cells. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `RVR-P2-009` | `modified` | Isolation and adversarial corpus. Current platform-specific launchers enforce or refuse their boundary. Repository negative controls and real provider lifecycle evidence answer different questions; repeat the required slice on the final candidate. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `#167` | `modified` | Deterministic bundle. Compiler tests verify native members, modes, exact pins, and deterministic containers. The current scoped provider lifecycle must bind the same bytes to its plan and effect. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `#185` | `modified` | Package release. `ADR-0146` ships one public wheel and sdist. The package release runbook owns candidate comparison, SBOM/checksums, attestation, publication, and clean-install evidence. Historical internal distributions are not active package dependencies. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `#172` | `modified` | Provider trust. Default acquisition verifies GitHub build attestations under the shipped policy (`ADR-0141`). Historical Ed25519 release coordinates are not the current estate. Rotation and rollback proof must name the trust mechanism actually used. | Owner: CLI/provider and release operations. Execute the applicable current candidate slice from the roadmap. |
| `RVR-P3-010` | `confirmed` | Resource leaks. `back-resource` remains mandatory. Platform logging now closes replaced owned handlers and has a real-process stdout/file regression; it is no longer an unowned handoff. | Owner: CLI and platform. Preserve resource and logging regression gates. |
| `RVR-P3-011` | `confirmed` | Obsolete completion plan. The roadmap is the sole current-plan owner. Historical issue closures and session statements are evidence to inspect, not executable requirements. | Owner: product maintenance. Keep the roadmap as the current-plan owner. |

## Evidence boundary

Repository checks prove the checked source and local fixtures. Native release
slices prove exact provider/consumer artifacts. Account-bound slices prove the
normal authenticated product path and require genuine browser device login.
Public deployment proof names the served SHA and schema. A past green result in
one category cannot close a different category or a newer candidate.

Current remaining actions and their status are maintained only in the roadmap.
Task authority follows `AGENTS.md` and `ADR-0150`; this historical record does not
add a separate confirmation before work already authorized by the user.
