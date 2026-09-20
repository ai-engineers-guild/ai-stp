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
| CLI expert registry | `apps/cli/src/ai_stp_cli/commands/`, `registry.py` | unclassified pending leaf audit |
| Local registry / passports | `apps/cli/src/ai_stp_cli/local/`, `packages/passports` | unclassified |
| Providers / install | `apps/cli/src/ai_stp_cli/provider/`, `provider-kit/` | kit `0.2.13`; unclassified specs |
| API `/v1` | `apps/api/`, `packages/contracts`, `schemas/v1` | unclassified |
| Platform | `apps/platform/` | unclassified |
| Web | `apps/web/` | unclassified |
| Deploy / CI | `deploy/`, `.github/workflows/`, `justfile` | ops docs synced 2026-09-20; code-backed |
| Auth / devices / grants | API slices + CLI account | unclassified |
| Catalog / publication / sync | platform + CLI | unclassified |
| Safety | `apps/platform/safety/` | unclassified |
| Colleague corporate | corporate specs/ADRs/tests | colleague |

## Specs already labelled

| Spec | Label | Reason |
| --- | --- | --- |
| SPEC-080 | code-backed | `SHIPPED_INTENT_NAMES` matches the drained intents on `main` |
| SPEC-074–077, 079, 081–086 | colleague | frozen |

All other `specs/active/` files are unclassified.

## Tests already labelled

| Path | Tag | Reason |
| --- | --- | --- |
| `tests/unit/test_cli_cloud.py` | replace | Module states the `#71` mock is the server; production API exists |
| `tests/unit/test_cli_catalog.py` | replace | Driven by the `#71` corpus as a fake catalogue |
| `tests/unit/platform/test_safety_coverage_boost.py` | replace | Named bulk coverage, not a behavior |
| `tests/contract/test_cli_process.py` | keep | Real CLI process |
| `tests/contract/test_implementation_status.py` | meta-oracle | Locks roadmap prose |
| `tests/contract/test_document_owned_facts.py` | meta-oracle | Locks contract markdown |
| `tests/contract/test_authority_surfaces.py` | meta-oracle | Locks agent-facing paths |
| `tests/unit/test_corporate_*.py`, `tests/api/platform/test_corporate_*.py` | colleague | frozen |
