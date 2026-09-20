---
description: "Rebuild specs, current docs, and tests from implemented code; archive unmatched history."
last_verified: "2026-09-20"
---

# ADR-0194: Rebuild the normative surface from implemented code

Status: accepted. Extends ADR-0001.

## Context

The working copy carries 86 active specifications (~1252 `REQ-*`), 182 ADRs,
hundreds of internal docs, and thousands of tests. Almost every specification
is still labelled active; `specs/archive/` holds two files. Several CLI tests
still drive journeys through the `#71` mock as if no server existed, while
production serves `/v1` from this tree.

The mismatch is the defect: agents and humans treat stale requirements as
current. Adding more specs on top of unimplemented or already-shipped behavior
makes the gap worse. ADR-0001 already requires a new ADR when the source of
truth changes. This is that change for the non-corporate product line.

Colleague corporate work (SPEC-074–077, SPEC-079, SPEC-081–086, ADR-0176 and
later corporate ADRs, `docs/engineering/corporate-*`, and matching tests) is
out of scope. This decision does not archive, rewrite, or close that zone.

## Options

1. Leave `specs/active/` as the source of truth and keep writing requirements
   ahead of code. Cost: the 1252 REQs already disagree with the tree.
2. Delete unmatched specs, ADRs, docs, and tests in one change. Cost: the docs
   gate, ADR supersession lint, and path-hardcoded contract tests fail; real
   invariants that exist only in old prose disappear with no ledger.
3. Classify against implemented code, archive unmatched narrative, keep ADRs as
   an append-only log with a binding default, rewrite remaining specs from
   code, and replace tests per surface when the replacement is green.

## Decision

Choose option 3.

For the non-corporate line, **what the system does** is defined by implemented
code, generated schemas and OpenAPI, and the tests that exercise them. An
active specification that disagrees with that evidence is not a current
requirement; it is either rewritten from the code or moved to `specs/archive/`.

`docs/archive/` holds historical plans, prototype snapshots, and checkpoint
novels. It is not edited semantically.

ADRs remain in `docs/adr/` and are not rewritten retroactively. Default: an
accepted ADR is binding until `docs/adr/binding.md` lists it as historical.
Colleague ADRs stay binding for that zone and are not migrated by this
program.

A machine-boundary change still needs an ADR when ADR-0001 says so, and still
needs an active spec **rewritten or added from the implementation in the same
change**. Spec-first work for behavior that already ships is refused.

Tests are replaced **per surface** in the same PR that deletes the old tests
for that surface. The destination suite mocks only true externals (GitHub,
OAuth, mail, indexes). It does not mock the unit under test. It does not drive
a live product journey exclusively through `ai_stp_contracts.mock`. Coverage
percentage still does not fail the gate (`ADR-0147`).

The classification ledger is `docs/engineering/implementation-canon.md`. Rows
are facts about the tree, not task checklists.

## Consequences

- `AGENTS.md` source-of-truth order follows this decision.
- `docs/documentation/zones.md` names `docs/archive/`.
- Meta-tests that hard-path a document must move with that document.
- Emptying `specs/active/` without a classified remainder fails `spec_lint`
  (`SP01`); archive happens in classified clusters, not as one dump.
- Production deploy is unchanged. This program does not promote until a later
  change actually alters runtime, which test and docs replacement must not.

## Revisit conditions

Revisit if the colleague corporate line is explicitly brought into this
program, if `specs/active` after classification cannot describe a shipped
machine boundary, or if a replacement test suite cannot fail when the product
path breaks.
