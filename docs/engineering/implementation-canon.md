---
description: "Classification of specs, docs, and tests against implemented non-corporate code."
last_verified: "2026-09-20"
---

# Implementation canon

Owner: `ADR-0194`. This ledger records how the non-corporate tree maps to
implemented code. It is not a roadmap and not a task list. A row is a fact:
**code-backed**, **historical**, **schema-duplicate**, **colleague**, or
**unclassified**. Unclassified stays in `specs/active/` / `docs/` until a
later PR proves it.

Colleague B2B is frozen. Do not classify those files for archive.

## Vocabulary

| Label | Meaning |
| --- | --- |
| code-backed | The code implements it; the spec or doc must be rewritten from that code or already matches |
| historical | Move to `specs/archive/` or `docs/archive/`; do not edit semantically after the move |
| schema-duplicate | Prose that only restates generated schemas/OpenAPI; the generated artifact is the owner |
| colleague | Corporate/B2B; out of scope |
| unclassified | Not yet proven; remains active/current |

Test tags used in later rows: **keep** (real I/O against live modules), **replace** (mock-era or coverage-boost), **meta-oracle** (freezes markdown paths), **colleague**.

## Frozen colleague set

| Kind | Identity |
| --- | --- |
| Specs | SPEC-074, SPEC-075, SPEC-076, SPEC-077, SPEC-079, SPEC-081, SPEC-082, SPEC-083, SPEC-084, SPEC-085, SPEC-086 |
| ADRs | ADR-0176 and later corporate ADRs |
| Docs | `docs/engineering/corporate-*`, `docs/operations/runbooks/corporate-bootstrap.md` |
| Branch | `feat/milestone-6-b2b-03` |
| Issues | #254, #256 — do not close from this program |

## Surfaces (code owners)

| Surface | Code | Notes |
| --- | --- | --- |
| CLI task engine | `apps/cli/src/ai_stp_cli/application/`, SPEC-080 | Eight drained intents on `main`; code-backed |
| CLI expert registry | `apps/cli/src/ai_stp_cli/commands/`, `registry.py` | ~35 command modules; leaf audit in P3 |
| Local registry / passports | `apps/cli/src/ai_stp_cli/local/` (~70 modules), `packages/passports` | code-backed |
| Providers / install | `apps/cli/src/ai_stp_cli/provider/`, `provider-kit/v3` | kit `0.2.13`; code-backed |
| API `/v1` | `apps/api/src/ai_stp_api/slices/` (24 slices), `packages/contracts`, `schemas/v1` | code-backed |
| Platform | `apps/platform/src/ai_stp_platform/` (content, legal, official_upstream, queue, safety, seo, storage) | code-backed |
| Web | `apps/web/` | code-backed |
| Deploy / CI | `deploy/`, `.github/workflows/`, `justfile` | ops docs synced 2026-09-20; code-backed |
| Auth / devices / grants | slices `auth`, `devices`, `grants`, `ownership` + CLI `device`, `cloud/grants` | code-backed |
| Catalog / publication / sync | slices `catalog`, `publish`, `sync` + CLI `local/sync_*` | code-backed |
| Safety | `apps/platform/safety/` | code-backed |
| Colleague corporate | corporate specs/ADRs/tests | colleague |

## Specs

Labels record whether implementing code exists, not REQ-level conformance;
the rewrite in phase 3 drops REQs the code does not enforce. Reasons name the
owning code.

| Spec | Label | Reason |
| --- | --- | --- |
| SPEC-001 | code-backed | Umbrella MVP scope; the tree ships it. P3 folds toward README/product |
| SPEC-002 | code-backed | `slices/auth`, `slices/devices`, `slices/grants`, `slices/ownership`; CLI `commands/device.py`, `cloud/grants.py` |
| SPEC-003 | code-backed | `packages/passports`, `commands/passport.py` |
| SPEC-004 | code-backed | `local/project_index.py`, `local/project_passport.py`, `commands/project.py` |
| SPEC-005 | code-backed | `local/versions.py`, `local/setup_versions.py`, `local/component_passports.py` |
| SPEC-006 | code-backed | `local/search.py`, `local/selection.py`, `local/composition.py` |
| SPEC-007 | code-backed | `apps/worker` `validate.py`/`publish.py`, `slices/publish` |
| SPEC-008 | code-backed | `provider/`, `provider-kit/v3`, `local/installation.py` |
| SPEC-009 | code-backed | `local/sync_merge.py`, `sync_state.py`, `sync_versions.py`, `slices/sync` |
| SPEC-010 | code-backed | `apps/api` slice tree serves `/v1` in production |
| SPEC-011 | code-backed | `commands/machine_help.py`, `skills/`, `application/` |
| SPEC-012 | code-backed | `toolchain/install.py` carries the uninstall/recovery paths |
| SPEC-013 | code-backed | `slices/documents`, `platform/legal` |
| SPEC-014 | code-backed | `toolchain/`, `docs_scripts/bootstrap_just.py` |
| SPEC-015 | code-backed | `packages/foundation` (`digests.py`, `identity.py`), `schemas/v1` |
| SPEC-016 | code-backed | `slices/reports`, `slices/complaints` |
| SPEC-017 | code-backed | `apps/api` shell (`session.py`, `deps.py`), observability in `deploy/` |
| SPEC-018 | code-backed | `apps/worker`, `platform/queue` |
| SPEC-019 | code-backed | `deploy/` runbooks and scripts; synced to live 2026-09-20 |
| SPEC-020 | code-backed | `platform/storage`, `migrations/`, `alembic.ini` |
| SPEC-021 | code-backed | `slices/catalog`, `tests/support/catalog_seed.py` |
| SPEC-022 | code-backed | `apps/web` app shell, landing, anonymous catalog |
| SPEC-023 | code-backed | `apps/web` account area + `slices/auth` |
| SPEC-024 | code-backed | `deploy/`, Dockerfiles, `infra-*` recipes |
| SPEC-025 | code-backed | `slices/sync`, CLI `local/sync_*` |
| SPEC-026 | code-backed | `slices/publish`, `slices/grants`, `slices/reports` |
| SPEC-027 | code-backed | `apps/web` owned-objects UI |
| SPEC-028 | code-backed | `slices/profile` + web public profile |
| SPEC-029 | code-backed | `passports/markdown.py` (strict profile) + `apps/web` `lib/markdown/passport.ts` (corpus-parity port, added 2026-09-20); documents renderer `contracts/safe_markdown.py` belongs to SPEC-031 REQ-3106 |
| SPEC-030 | code-backed | `commands/link.py`, `contracts/web_projections.py`, registry deep links |
| SPEC-031 | code-backed | `slices/documents` |
| SPEC-032 | code-backed | `slices/health`, `platform/safety`, ops runbooks |
| SPEC-033 | code-backed | `slices/technology`, device challenge freshness |
| SPEC-034 | code-backed | `apps/web` catalog search |
| SPEC-035 | code-backed | `apps/web` component page, media, reactions |
| SPEC-036 | code-backed | `slices/schemas`, `docs_scripts/skill_projections.py` |
| SPEC-037 | code-backed | `registry.py`, `commands/` catalog/onboarding leaves |
| SPEC-038 | code-backed | `cloud/grants.py`, `cloud/reports.py`, `commands/` publication leaves |
| SPEC-039 | code-backed | `local/sync_merge.py`, `sync_state.py` |
| SPEC-040 | code-backed | `local/evaluation.py` |
| SPEC-041 | code-backed | `local/setup_scaffold.py`, `commands/component.py` scaffold |
| SPEC-042 | code-backed | `local/store_ports.py` |
| SPEC-043 | code-backed | `local/impact.py`, `local/report_plans.py` |
| SPEC-044 | code-backed | `apps/worker` `github_archive.py`, `local/github_evidence.py` |
| SPEC-045 | code-backed | `packages/sources` |
| SPEC-046 | code-backed | `apps/web` feature registry and content hub |
| SPEC-047 | code-backed | `apps/web` backend consumer surfaces |
| SPEC-048 | code-backed | `apps/web` RSC/fetch boundaries |
| SPEC-049 | code-backed | `slices/github_connector`, `rate_limit.py` |
| SPEC-050 | code-backed | `local/external_sources.py`, `packages/sources` |
| SPEC-051 | code-backed | `platform/seo` metrics, `slices/catalog` usage counters |
| SPEC-052 | code-backed | `slices/complaints` |
| SPEC-053 | code-backed | `platform/seo`, `apps/worker` `seo_build.py`, `slices/seo` |
| SPEC-054 | code-backed | `slices/content`, worker handlers |
| SPEC-055 | code-backed | `platform/legal`, `slices/auth/onboarding.py` |
| SPEC-056 | code-backed | `contracts/official_manifest.py`, `platform/official_upstream` |
| SPEC-057 | code-backed | `local/embedded.py`, `embedded_promotion.py`, `embedded_update.py` |
| SPEC-058 | code-backed | `local/multi_root.py`, `multi_root_orchestrator.py`, `application/install_transaction.py` |
| SPEC-059 | code-backed | `slices/ownership`, catalog line identity in `slices/catalog` (active file; number shared with archived SPEC-059) |
| SPEC-060 | code-backed | `contracts/standard.py`, family handling in `application/` |
| SPEC-061 | code-backed | `application/qualify.py`, `release_scripts` estate record |
| SPEC-062 | code-backed | `local/setup_recast.py` |
| SPEC-063 | code-backed | `local/component_materialize.py` (active file; number shared with archived SPEC-063) |
| SPEC-064 | code-backed | `packages/assurance`, `local/embedded*.py` |
| SPEC-065 | code-backed | setup-family alignment in `application/` + `contracts/standard.py` |
| SPEC-066 | code-backed | `foundation/adaptations.py`, `local/evaluation.py` |
| SPEC-067 | code-backed | `local/cli_program.py` |
| SPEC-068 | code-backed | `local/preserved_setups.py` |
| SPEC-069 | code-backed | `commands/environment.py`, `foundation/harnesses.py` |
| SPEC-070 | code-backed | `commands/environment.py`, `commands/doctor.py` |
| SPEC-071 | code-backed | private distribution path in `local/` + `tests/support/private_distribution.py` |
| SPEC-072 | code-backed | `self_update/` |
| SPEC-073 | code-backed | `slices/github_connector`, `commands/github.py` |
| SPEC-074 | colleague | frozen |
| SPEC-075 | colleague | frozen |
| SPEC-076 | colleague | frozen |
| SPEC-077 | colleague | frozen |
| SPEC-078 | code-backed | `local/project_links.py`, `slices/sync`; not in the frozen set |
| SPEC-079 | colleague | frozen |
| SPEC-080 | code-backed | `SHIPPED_INTENT_NAMES` matches the drained intents on `main` |
| SPEC-081 | colleague | frozen |
| SPEC-082 | colleague | frozen |
| SPEC-083 | colleague | frozen |
| SPEC-084 | colleague | frozen |
| SPEC-085 | colleague | frozen |
| SPEC-086 | colleague | frozen |

## Docs

Cluster-level labels; per-file refinement happens in phase 2.

| Cluster | Label | Reason |
| --- | --- | --- |
| `docs/operations/`, `docs/operations/runbooks/` | code-backed | Synced against live deployment 2026-09-20 (#311, #312) |
| `docs/documentation/` | code-backed | Zone rules and lint suite own this tree |
| `docs/adr/` | code-backed | Append-only log; `binding.md` defaults accepted to binding |
| `docs/engineering/` working rules — `coding-rules`, `dependency-policy`, `failure-catalog`, `git-workflow`, `quality-gates`, `repository-structure`, `schema-evolution`, `tech-debt-rules`, `tech-stack`, `testing`, `web-quality`, `github-connector-operations`, `release-evidence` | code-backed | Rules the gate or the team enforces today |
| `docs/archive/*-implementation-plan.md` — `article-publication`, `artifact-storage-private-delivery`, `github-connector`, `official-registry-identity-and-requests`, `seo-publication` | historical | Plans whose code ships; archived 2026-09-20 |
| `docs/engineering/agent-ux-implementation-plan.md` | unclassified | Live contract of open epic #261; not shipped, not dead |
| `docs/engineering/` working evidence — `implementation-roadmap`, `catalog-search-benchmark`, `cli-performance`, `real-provider-evidence`, `first-party-corpus`, `federated-source-threat-model` | code-backed | Live procedure/plan/threat-model docs read 2026-09-20 |
| `docs/archive/audit-remediation-status.md`, `docs/archive/runner-separation-readiness.md` | historical | A retained audit disposition and a dated readiness snapshot; archived 2026-09-20. The contract test retargeted to the archive path now guards its immutability |
| `docs/engineering/corporate-*` | colleague | frozen |
| `docs/contracts/` (60 files) | code-backed | Read 2026-09-20: semantic contracts (closed lists, state machines, privacy, idempotency, authority pointers) that generated schemas do not express; per-file schema-duplicate review folds into P3 |
| `docs/product/`, `docs/architecture/`, `docs/agent/` | code-backed | Current-zone docs describing the shipped product, architecture, and agent surface |
| `docs/references/` | code-backed | Citation list and prototypes; pruned with use, not archived wholesale |
| `docs/archive/` | code-backed | The zone itself is the destination |
| `docs-user-facing/` | code-backed | Separate shipped surface; links into the canon, does not copy it |

## Tests

| Path | Tag | Reason |
| --- | --- | --- |
| `tests/unit/test_cli_cloud.py` | keep | The `#71` corpus as wire cases — malformed/refused/slow responses a client must reject — plus retry pacing and local session rules; the sign-in and account journeys live in `tests/api/cli/` against the real app |
| `tests/unit/test_cli_catalog.py` | keep | Client-boundary only after strangler: injected transports (offline, tampered, cursor opacity) and local cache rules; journeys moved to `tests/api/cli/test_catalog.py` over the real seeded catalog |
| `tests/unit/test_cli_account.py` | keep | Application-seam stubs (`begin`/`complete_once`/`sync_now`) for question shape, replay, and the decline path the API deliberately does not expose; journeys moved to `tests/api/cli/test_account_tasks.py` |
| `tests/unit/test_cli_owner.py` | keep | Command-registry declaration only; the list/detail/version journeys moved to `tests/api/cli/test_owner.py` against the real `/v1/owner` routes over the seeded corpus |
| `tests/unit/test_cli_grants.py` | keep | Wire contract and confirmation gates only; grant/invitation journeys moved to `tests/api/cli/test_grants.py` against the real `/v1/grants` routes |
| `tests/unit/test_cli_reports.py` | keep | Preview durability, digest gate and fail-closed diagnostics; create/list/read and idempotent replay moved to `tests/api/cli/test_reports.py` against the real `/v1/requests` routes |
| `tests/unit/test_cli_publication.py` | keep | Wire/retry/local gates only; plan create/bind/confirm journeys moved to `tests/api/cli/test_publication.py` against the real `/v1/publications/plans` routes |
| `tests/unit/test_cli_private_distribution.py` | keep | Off-contract refusal and changed-hash gate only; `publication plan`/`visibility` journeys moved to `tests/api/cli/test_private_distribution.py` — the first command-level (not transport-level) real boundary, sending a locally authored passport |
| `tests/unit/test_cli_artifact.py` | keep | Client-local fault injection only (truncation, flood, timeout, tampered cache, wire path); the fetch journeys moved to `tests/api/cli/test_artifact.py` against the real artifact route and object store |
| `tests/unit/test_cli_sync_transport.py` | keep | Real-SQLite local seams (event preparation, page application, cursors, merge mechanics) plus `MockTransport` at the client seam only (receipt recording, retry, revocation mapping); push/pull/conflict/merge journeys moved to `tests/api/cli/test_sync.py` against the real `/v1/sync` routes — where a conflicted ancestor blocking its own merge surfaced and was fixed |
| `tests/unit/test_cli_commands.py` | keep | Environment fault injection (`shutil.which`, `sys.version_info`, wheel metadata) against real local state — no fake server |
| `tests/unit/test_cli_local_registry.py` | keep | Failure injection (`MIGRATIONS`, `commit`) on the real SQLite registry — doubles simulate faults, not a service |
| `tests/unit/test_cli_projects.py` | keep | Real filesystem discovery; one `DISCOVERY_ENTRIES` bound override |
| `tests/unit/platform/test_safety_adapter_edges.py` | keep | Adapter edge-branch tests on real inputs; renamed from `test_safety_coverage_boost.py` (the name described intent, not the tests). Blanket pyright suppression removed; S3 stays mocked as a true external boundary |
| `tests/contract/test_cli_process.py` | keep | Real CLI process |
| `tests/api/cli/` | keep | CLI↔API boundary: the real `/v1` app served synchronously (`tests/support/asgi_sync.py`) over an isolated migrated PostgreSQL database (`tests/support/postgres.py`, shared by the platform conftests) |
| `tests/unit/test_http_contract.py`, `test_catalog_contract.py`, `test_auth_identity_contract.py`, `test_health_contract.py` | keep | Wire-parity of `packages/contracts` against the `#71` corpus as fixture data, not as a fake server |
| `tests/unit/platform/test_catalog_seed.py`, `tests/support/catalog_seed.py` | keep | Real seed path against the corpus |
| `tests/contract/platform/test_dto_issue71_equivalence.py`, `test_conformance.py`, `test_openapi.py` | keep | Corpus as wire examples for schema/OpenAPI parity |
| `tests/contract/test_implementation_status.py` | meta-oracle | Locks roadmap prose |
| `tests/contract/test_document_owned_facts.py` | meta-oracle | Locks contract markdown |
| `tests/contract/test_authority_surfaces.py` | meta-oracle | Locks agent-facing paths |
| `tests/contract/test_alpha_contract_baseline.py` | meta-oracle | Locks contract baseline docs |
| `tests/contract/test_audit_remediation_status.py` | meta-oracle | Locks the audit-status doc |
| `tests/contract/test_user_docs_*.py` | meta-oracle | Lock user-docs copy and parity |
| `tests/contract/test_protocol_vocabulary_owner.py`, `test_harness_support_tiers.py`, `test_failure_catalog_owners.py` | meta-oracle | Lock ownership tables in docs |
| `tests/contract/test_offline_closure.py`, `test_publish_pypi_workflow.py`, `test_deploy_contract.py`, `test_git_identity_policy.py`, `test_config_contract.py`, `test_environment_contract.py` | keep | Real invariants over workflows, imports, and deploy paths; not prose-freezers |
| `tests/unit/test_corporate_*.py`, `tests/api/platform/test_corporate_*.py` | colleague | frozen |
| All other `tests/` files | keep | Default: they ran green against real code on 2026-09-20; P4 re-tags per surface when a replacement lands |
