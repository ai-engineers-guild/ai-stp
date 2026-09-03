---
description: "SPEC-001: MVP product contract."
last_verified: "2026-08-24"
---

# SPEC-001: MVP Product Contract

## Purpose

The user installs `ai-stp`, works with it through their agent, and completes the full local path from a passport and project index to a verified setup, installation, and recovery without requiring a web interface.

## Scope

The MVP includes a local registry, anonymous reads from the public registry, private synchronization after sign-in, publication, seven supported harnesses, and a limited `undefined` mode.

Real payments, the enterprise landscape, a sophisticated web editor, and claims of an object's absolute safety are out of scope.

The first supported alpha line is `0.0.16` under `ADR-0142`. Its release
evidence covers Linux, macOS and Windows on `x86_64` and `arm64`; a missing,
skipped or inconclusive required row does not support a release claim.

## Terms

- **Primary support** — the complete end-to-end scenario and release evidence for harnesses marked `primary` in `SUPPORT_TIERS`; blocks the first MVP release.
- **Beta support** — the same safe lifecycle, but native harness surfaces marked `beta` may have incomplete support; the line advances independently and does not block the first release.
- **`undefined`** — an unknown harness. It and its native configurations are recorded as an observation so the user can see what they have; managed objects are not created for it, and application is impossible.

## Requirements

- `REQ-101`: The primary machine client is an agent operating through a strict JSON CLI.
- `REQ-102`: The complete local path does not require an account or server mode.
- `REQ-103`: The public registry can be read without authorization.
- `REQ-104`: Private synchronization, granting access, and publication require authorization.
- `REQ-105`: Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor, Antigravity, and the limited `undefined` identifier are supported.
- `REQ-106`: Harnesses at the `primary` tier complete the primary end-to-end scenario; harnesses at the `beta` tier complete the beta scenario without weakening plan, backup, or restore. Tier membership belongs to `SUPPORT_TIERS` and `SPEC-033`, not to this requirement.
- `REQ-107`: The primary creation, compilation, and installation path does not require switching to the web interface.
- `REQ-108`: Payments and the enterprise landscape are excluded from the MVP. Windows is not excluded: it is implemented and declared as a requirement by `SPEC-014` `REQ-1419`; what is missing is recorded run evidence, not support, and its absence does not raise the claimed support level under `REQ-110`.
- `REQ-109`: The first MVP release is blocked by incomplete product requirements and by the absence of complete end-to-end evidence for Claude Code and Codex across the declared matrix; incomplete beta lines do not block the release.
- `REQ-110`: The claimed support level does not exceed the observed evidence; a line without a run receives `not_verified`.
- `REQ-111`: A missing required environment variable does not block installation, but changes launch readiness to `needs_configuration` until it is provided.
- `REQ-112`: After successful initial setup, the local path works without a network connection, while operations that require a network are declared separately and return a typed reason.
- `REQ-113`: The seven harnesses are the complete MVP support set (`ADR-0120`); a new official `harness_id` appears only through the platform promotion process under `ADR-0033`, and user-defined adapters are not published as official support.
- `REQ-114`: The first release is additionally blocked by an incomplete first-party launch catalog under `docs/engineering/release-evidence.md`; catalog completeness is a release barrier, not a schema invariant.
- `REQ-115`: The public CLI release consists of aligned versions of foundation, passports, assurance, contracts, sources, and CLI; wheel and sdist artifacts are reproducible, include metadata/LICENSE, and are accompanied by an SBOM, checksums, and provenance for the exact SHA; install smoke pins all six distributions to exact candidate wheels and runs outside the checkout.
- `REQ-116`: After one-time Trusted Publisher and access bootstrap, an immutable release plan bound to an exact main SHA drives resumable publication of the six-package dependency closure and publishes CLI last. An existing version is continued only when every remote artifact digest equals the candidate; ordinary CI/deploy jobs and local machines have no long-lived PyPI credential or publish authority.
- `REQ-117`: The supported alpha release is proven on Linux, macOS and Windows on `x86_64` and `arm64`; every mandatory row is present and conclusive.
- `REQ-118`: `0.0.16` is the first supported alpha contract. Earlier published alpha bytes and history remain immutable evidence but are not runtime compatibility obligations; the HTTP namespace remains `/v1`, while a changed canonical machine form receives an explicit schema and hash-domain identity.

## States and errors

The local path distinguishes `ready`, `needs_input`, `degraded`, `unsupported`, and `failed`. An unavailable server does not block local reads or access to already saved objects.

An unknown harness produces `unsupported` readiness on this axis and the separate `AI_STP_UNSUPPORTED_APPLY` error code when application is attempted. The axis state and error code belong to different axes under `architecture/principles.md` and are not conflated.

## Security and privacy

An unverified object is excluded from automatic composition. Secrets, source conversations, and environment values are not written to passports. Every mutating operation uses a plan, an exact digest, and separate confirmation according to the risk rules.

## Compatibility and migration

The CLI, API, schemas, and provider protocol have independent versions. Supported client versions are published before server mode is enabled. Changing the harness list, primary path, or MVP boundary requires a new ADR and updates to all related specifications.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-101` | A contract test verifies machine JSON and operation of the canonical Agent Skill. |
| `REQ-102` | An E2E test with the network disabled creates a passport, index, composition, and local record. |
| `REQ-103` | An API/CLI test searches for and retrieves a public object without a token. |
| `REQ-104` | Negative auth tests reject private synchronization and publication without a session. |
| `REQ-105` | An enum/schema test accepts exactly seven identifiers and `undefined`. |
| `REQ-106` | Recorded E2E tests complete install, launch, status, and restore across the support matrix. |
| `REQ-107` | The primary E2E test for creation, compilation, and installation runs only through the CLI and provider, without browser automation. |
| `REQ-108` | A scope check and dependency search confirm the absence of billing and enterprise runtime paths; Windows paths are expected, and their presence is not a defect. |
| `REQ-109` | The release checklist is blocked by missing Claude Code and Codex evidence and is not blocked by missing beta evidence. |
| `REQ-110` | The support status generator does not assign a verified level to a beta line without a recorded run. |
| `REQ-111` | A fixture with a missing named variable permits installation and produces `needs_configuration` at launch. |
| `REQ-112` | A check with the network disabled completes declared offline operations and produces a typed reason for networked operations. |
| `REQ-113` | An enumeration check rejects an eighth value without a new ADR and schema version, while an inventory finds no path for publishing a user-defined adapter as official support. |
| `REQ-114` | The release checklist includes a launch catalog inventory, and missing or expired evidence for any object in it blocks the release. |
| `REQ-115` | The candidate builder builds six wheel/sdist pairs twice, compares bytes, verifies metadata, and creates deterministic SBOM, manifest, and checksums; a separate smoke verifies PEP 610 provenance for all six exact wheels, machine commands, and uninstall outside the checkout; the public workflow publishes provenance. |
| `REQ-116` | A rehearsal interrupts publication between packages, resumes only after exact remote-digest comparison, publishes CLI last, and proves that ordinary CI/deploy jobs hold no long-lived publication credential. |
| `REQ-117` | The release matrix contains conclusive Linux, macOS and Windows rows for both architectures and rejects a missing, skipped or inconclusive row. |
| `REQ-118` | Contract vectors reject silent reinterpretation of an earlier content-addressed alpha object while the current `/v1` client and server agree on the first supported schema set. |
