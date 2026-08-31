---
description: "Primary user flows and system behavior on errors."
last_verified: "2026-08-04"
---

# User flows

## First run

```text
user copies the command from the website
→ CLI is installed through uv
→ local data directory is created
→ device is registered
→ harnesses and tools are discovered
→ discovered environment is recorded in the Device Passport
→ complete mvp-full toolset is installed
→ Agent Skill is installed
→ agent completes the Developer Passport: preferences and decisions
```

## New project

```text
Agent runs ai-stp in an empty or docs-only folder
→ system identifies a new project
→ Agent asks about the goal, stack, and constraints
→ Project Passport is created
→ search, filters, and selection yield eligible candidates
→ Agent creates composition proposals and displays reports
→ user confirms one proposal
→ private SetupVersion is fixed and pinned to the project
→ user confirms the installation plan
→ provider applies the setup
```

Proposals are short-lived: until the user confirms one, no version, target, or registry entry is created. The agent decides how many proposals to show.

## Existing project

```text
indexing manifest/lock/config/AI files
→ current setup discovery
→ comparison with developer and device passports
→ eligible candidates and their trust lines
→ adaptation and assembly
→ backup/apply/status
```

## Existing configuration

```text
read current native configuration without changing it
→ backup by the provider
→ secret removal and file inventory
→ personal setup for this harness
→ passport, exact file hashes, and provenance
→ local verification
→ record in local registry
→ select or restore later
```

The backup reference and imported personal setup remain separate objects: the former belongs to the provider, the latter to the registry.

## Discovering and accepting components

```text
CLI shows global and project components
→ classifies kind, source, and scope
→ user chooses what to accept
→ YAML passport is created next to the component
→ verification
→ registration in local catalog
```

Nothing is imported automatically. Secret values are not read. Bulk migration and cloud import are not part of the MVP.

## Author flow

```text
local component or setup
→ discovery
→ YAML passport next to the object
→ verification
→ local registration without an account
→ optional publication from an exact GitHub commit
```

The launch catalog is populated with the guild's first-party objects according to the `ADR-0034` release barrier; user publications supplement it. Platform-authored packaging of third-party open-source components is not performed in the MVP: third-party work enters the catalog only when published by its author.

Publishing a project-local component uses an explicit component root and the list of permitted files from its passport. An exact file inventory is shown before publication; paths outside the root, links, secret-like files, binary files, and undeclared files are rejected.

## Access, fork, and derivative publication

```text
owner grants access to major line X
→ recipient reads and installs versions X.*
→ new line X+1 requires a new grant
→ fork creates a new private setup for the recipient
→ derivative publication requires a substantive change and complete verification
→ revocation stops future reads without affecting local copies and targets
```

The recipient does not edit the original: they make every change of their own in a fork. An unchanged clone cannot be republished under a new namespace, and private third-party bytes are not published unchanged. After revocation, rebuilding with an inaccessible private dependency ends with a precise access error.

## Publication

```text
local draft
→ complete passport and non-empty tags
→ verification according to the verification policy matrix
→ credential-dependent checks run locally with the author's credentials
→ signed author attestation of the exact digest
→ exact Git commit and subpath for the public object
→ server digest/structure validation and repetition of credential-free checks
→ publication of immutable X.Y
```

An incomplete draft can synchronize privately but does not appear in the catalog. A required check without current accepted evidence — `failed`, `degraded`, `not_run`, or `expired` — blocks publication entirely.

## Daily work

```text
status → rescan → search → diff → update → rollback
```

`status` shows the project, setup, harness, selected and installed versions, pending installation state, and both kinds of drift together with missing required environment variables. The drift types differ: `local_drift` means the target was changed outside the provider, while `catalog_drift` means a newer version is available; waiting to install a newly confirmed version is the `pending_install` state, not drift. None resolves itself. `rescan` updates local findings — observations not yet entered in the passport. `search` finds available versions and components. `diff` shows changes in composition and requirements. `update` is always performed by user decision, creates a new version, and is applied after a plan. `rollback` restores the entire previous confirmed version.

The MVP has no automatic updates, release channels, complex update policies, or background daemon. Previous versions are stored only for comparison and rollback.

## Reporting an object

```text
user notices harmful behavior or a recurring failure
→ web action or CLI command collects mechanical fields
→ complete preview and explicit consent
→ one closed ReportCase is created
→ moderators perform triage
→ author receives a sanitized notification when necessary
→ vulnerability is escalated into a closed process
```

A report does not create a public issue or block the object by itself: hiding and blocking remain auditable moderator actions. Source code, prompts, secrets, and full paths are not included in a report automatically; its contents are limited by `docs/contracts/report-case.md`.

## Unverified author

By default, results contain only the authoritative trust lane. Objects from unverified authors appear in a separate section only after explicit user consent and are not moved into the authoritative lane either automatically or by agent decision. Installing such an object requires local verification and a separate decision.

An empty authoritative lane is an honest result and does not enable the experimental lane by itself.

Consent applies to a command or session. A durable exception is created only through an explicit scope choice — publisher or object major line — and ceases to apply for a new major line or an expansion of permissions, network access, or credentials.

## Errors

| Situation | Behavior |
|---|---|
| Plan is stale | apply is blocked and a new plan is built |
| Setup conflicts | ConflictReport is returned and no write is performed |
| Provider does not support the surface | conversion receives `unsupported` and installation is blocked |
| Check did not run | status is `not_run` or `degraded` |
| Apply completed partially | operation is marked `partial` and automatic retry is prohibited |
| Device is revoked | cloud access ends and local data remains available |
| New target does not launch | restore of the previous target is activated |
| Required environment variable is missing | installation is possible with a warning; launch readiness is `needs_configuration` |
| Installed version is blocked | new installations and updates are prohibited; the current target is not disabled |
| Version evidence expired or failed | version loses verification and eligibility, new installations and updates are blocked, and the installed target operates with a warning |
| Harness is unsupported | readiness is `unsupported`, apply returns `AI_STP_UNSUPPORTED_APPLY`; no objects are created |
| Harness itself was changed outside the provider | `local_drift`: the provider owns the program lifecycle; a change outside it requires a user decision |
