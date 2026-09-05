---
description: "Product entities, their ownership, and core invariants."
last_verified: "2026-09-05"
---

# Domain Model

## Identity and Devices

| Entity | Meaning |
|---|---|
| Account | An internal platform user. |
| OAuthIdentity | A linked Google or GitHub identity. |
| PublicProfile | A separately maintained public object, not a passport projection. |
| Device | A CLI installation with its own ID and key. |
| AccessGrant | The right of an account ID to access a private object or major line. |
| GrantInvitation | An invitation sent to a verified email address before a grant exists. |
| AuditEvent | An immutable record of a sensitive action. |
| ReportCase | A private report case with mechanical evidence and auditable moderation. |

## Passports and Projects

| Entity | Meaning |
|---|---|
| DeveloperPassport | A private cross-device profile of preferences and decision history. |
| DeveloperPassportRevision | An immutable passport revision. |
| DevicePassport | A private passport for one device environment: OS, architecture, harnesses, and tools. |
| DevicePassportRevision | An immutable device-passport revision. |
| Project | A registered local project. |
| ProjectPassport | Structured project facts and requirements. |
| ProjectIndex | An index of a restricted set of safe files and symbols. |
| Fact | A value with provenance, confirmation, and source references. |

## Registry

| Entity | Meaning |
|---|---|
| Component | A stable logical component entity with a closed `component_type`. |
| ComponentVariant | A native component implementation for one harness. |
| ComponentVersion | An immutable `X.Y` version. |
| Setup | A stable logical setup entity belonging to one harness. |
| SetupVersion | An immutable setup version. |
| SetupLineage | An optional provenance relationship between setups for different harnesses. |
| DraftRevision | Mutable private history before freeze/publish. |
| Artifact | Content-addressed bytes with an exact hash. |
| ValidationSnapshot | Validation results for an exact digest. |
| EvidenceBinding | The accepted source of time-bounded evidence for one required check. |
| PublicationPlan | An immutable server-side publication plan (Operation) with a plan_hash. |
| Article | A stable content-hub item with exactly one source owner: `repository` or `staff`. |
| ArticleRevision | An immutable localized Article revision with a canonical digest and provenance. |
| ArticleActive | Active RU/EN pointers for a published Article. |
| SeoFactSnapshot | An immutable allowlist projection of public facts for an exact subject revision and locale. |
| SeoRevision | An immutable presentation representation of a snapshot with generator provenance. |
| SeoActiveRevision | The single active presentation pointer for a subject and locale. |

## Compilation

| Entity | Meaning |
|---|---|
| SelectionRun | Context, questions, candidates, and decisions. |
| SelectionProposal | A derived, short-lived composition proposal within a recommendation session. |
| UnverifiedConsent | A durable consent record scoped to a publisher, object major line, or authorized full-task profile. |
| RecommendationTrace | The trust lane, consent source, and reasons for selecting a candidate. |
| SetupGraph | Component nodes and dependencies. |
| Overlay | A constrained change on top of an upstream version. |
| Conflict | An unresolved contradiction. |
| CompositionReport | Why each component was selected. |
| ConversionReport | The completeness of native adaptation. |
| HarnessBundle | A validated package for the provider. |

## Installation

| Entity | Meaning |
|---|---|
| ProviderRelease | An exact version of a public setup manager. |
| HarnessTarget | An isolated runtime/configuration directory. |
| ImportedSetup | A personal setup created from an existing native configuration. |
| InstallPlan | A side-effect-free plan with a digest and preconditions. |
| Operation | A durable plan/apply/verify lifecycle. |
| InstallationSnapshot | State before and after an operation. |
| BackupRef | A reference to a provider-owned backup. |
| ActiveTargetPointer | The selected target for the next launch. |

## Synchronization

| Entity | Meaning |
|---|---|
| EntityRevision | A content-addressed revision with parents. |
| DeviceHead | The latest known entity revision on a device. |
| ServerHead | The current revision accepted by the server within one account. |
| SyncCursor | A position in the accepted server stream. |
| LocalOutboxEvent | A local change awaiting upload. |
| ServerOutboxEvent | An ordered record of a server-accepted change for pull. |
| SyncReceipt | A durable, idempotent result for one server sync event. |
| Tombstone | An explicit deletion. |
| ConflictRecord | An unresolved concurrent change. |

## Data Ownership

| Data | Owner |
|---|---|
| Target files | local harness provider |
| Installation state | device |
| Local draft | local registry; cloud copy is optional |
| Published metadata and version | server |
| Visibility, grants, verified badge | server |
| Project index | device; cloud only after opt-in |
| Backup bytes | provider on the device |
| Passport creation and installation | CLI and the user's Agent |
| Account, privacy, devices, and publication | shared web and CLI scenario |

## Invariants

- DeveloperPassport is private by default.
- Observable environment facts belong to DevicePassport; DeveloperPassport does not contain them.
- Device passports are not merged across devices; only DeveloperPassport is merged across devices.
- PublicProfile is maintained separately and does not receive passport fields automatically.
- A fact stores provenance and confirmation as two independent axes.
- A published version is immutable.
- Version `X.Y` is not reused for a different digest.
- A Setup belongs to one `harness_id`, fixed at creation.
- SetupVersion identity does not contain a variant; relationships between setups are expressed through SetupLineage.
- SetupVersion pins an exact ComponentVersion.
- SelectionProposal is short-lived; SetupVersion is created only from explicit user confirmation.
- Component dependencies are split into `requires_components` and `requires_capabilities`.
- A major line defines the future access boundary.
- A grant recipient may read, install, and fork, but may not edit the original.
- An unchanged clone is not republished; derivative publication requires a substantive change.
- InstallationSnapshot does not duplicate backup bytes.
- BackupRef and ImportedSetup remain distinct objects.
- A device signature is not platform-executed validation.
- An unverified object enters results only with explicit consent and never enters the authoritative lane.
- A consent record is scoped to a publisher, object major line, or authorized full-task profile; fingerprint expansion revokes publisher and object-major coverage, not an active task grant.
- `author_verified` and `component_verified` are independent axes.
- AccessGrant is not created merely from knowledge of an account ID or email address.
- Report count alone does not change a version's lifecycle; hiding and blocking are auditable moderator actions.
- Installability is derived from current required evidence and does not disable installed targets.
- A published version is not merged; a new version is released.
- An Article's source owner does not change on import or staff publication; an identity collision with another owner is rejected.
- An SEO revision does not change a passport, article body, trust, or lifecycle; model-generated presentation is activated only after a deterministic base revision and fact validation.
