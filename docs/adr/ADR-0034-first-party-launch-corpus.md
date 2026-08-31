---
description: "Decision to make the first-party launch catalog a measurable release barrier with a verified Guild namespace."
last_verified: "2026-08-28"
---

# ADR-0034: First-party launch catalog

Status: accepted.

## Context

The catalog had been described as populated by "the platform owners' own components and user publications," without a measurable boundary. At the same time, the product deliberately declined to package third-party open-source components on their authors' behalf: third-party work enters the catalog only through author publication. This correct decision increases launch dependence on first-party content, whose composition was nowhere defined as a release requirement.

Without a boundary, a technically ready platform may launch with an empty or unrepresentative catalog: search and recommendation return nothing, leaving no way to validate the product's main value.

## Options

1. Rely on organic publications. No work now, but a cold start with empty results.
2. Encode object counts in schemas and domain invariants. Guarantees composition but turns launch content into a permanent product constant.
3. Define launch catalog composition as a measurable release barrier in release evidence without changing schemas.

## Decision

Option 3 is accepted.

**The launch catalog is first-party.** It is published from the verified AI Engineers Guild platform namespace; providers remain NDDev products unless a specific object explicitly names another publisher. User publications supplement the catalog, but launch does not depend on them.

**Launch composition is measurable:**

```text
baseline setups — one for each supported harness

reusable first-party components
sufficient to build those setups
```

**Amendment dated 2026-08-28: role families are removed from launch composition.**

This section previously required "role families for Claude Code and Codex—six for each, as separate harness-specific setups: backend, frontend, full-stack, code review, security, research," and they were released: 60 components and 12 setups. Their sources—`rldyour-claudecode` and `rldyour-codex`—were moved to a personal account and archived on 2026-08-25. `source` and commit are part of the content-addressed passport, and a published `X.Y` is immutable (`REQ-2606`), so provenance cannot be repaired by editing: that would release different objects. There is no live repository from which to rebuild them.

The requirement, not the record, is removed: released objects remain published and readable. The launch barrier is now baseline setups for all supported harnesses (`ADR-0120`: seven, not five) plus a sufficient component set; the corpus rebuilt by the setup compiler from the live estate contains 33 components and 7 setups.

If role families return, they need a live source and will enter here through a new amendment naming it, not by restoring this paragraph.

**Every launch object is evidenced.** A complete passport, provenance, current mandatory evidence under validation policy, and compatibility and installation evidence—the same requirements as any publication; the launch catalog receives no exemptions.

**The launch corpus is published through the normal path.** A complete `ai_stp_contracts.first_party` snapshot follows the existing sequence `publication plan` → bind exact bytes → confirm exact hash → server validation → publication, components first and dependent setups second. The operator batch only resumes this sequence and collects the final report; it neither writes the catalog directly nor introduces a separate policy. The experimental seed from `SPEC-021` remains a fixture/demo mechanism and is not a launch-catalog release path.

**Counts do not enter schemas.** Catalog composition is a release and content barrier in `docs/engineering/release-evidence.md`, not a domain-model invariant: schemas do not know how many setups must exist.

**Content is not invented in documentation.** This record defines the form and barrier; concrete component and setup bytes are created in a separate content stage against real harnesses and validated as ordinary publications.

## Consequences

- `docs/engineering/release-evidence.md` receives a launch-catalog section with a checklist;
- `SPEC-001` blocks the first release when the catalog is incomplete;
- the roadmap receives a content stage and an entry in the intentionally-unwritten list;
- release quality barriers reference the catalog inventory.

## Reconsideration conditions

This decision will be reconsidered after launch validation: if the composition proves insufficient to demonstrate value or excessive in maintenance cost, its form will be adjusted by a new decision—still as a release barrier, not a schema constant.
