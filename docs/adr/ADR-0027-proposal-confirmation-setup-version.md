---
description: "Decision to make composition proposals short-lived and create a SetupVersion only from explicit confirmation."
last_verified: "2026-08-09"
---

# ADR-0027: Composition proposals and a confirmed SetupVersion

Status: accepted.

## Context

`SPEC-006` defines `SelectionRun`, candidates, and trust lines, while `ADR-0022` establishes that the user's agent, not a model inside `ai_stp`, composes the setup. However, the transition from a composition option shown by the agent to an installable object is undefined: who decides how many options to show, whether shown options outlive the session, where the confirmation boundary lies, and exactly what is fixed when the user consents.

Without this boundary, an implementation may persist every shown option as a version, apply an unversioned temporary composition outside `REQ-1110`, or lose reproducibility between recommendation and installation after candidates change.

## Options

1. Store every shown proposal as a durable object. This provides history but clutters the registry with versions nobody selected and makes "show" indistinguishable from "create."
2. Apply the confirmed composition directly, without a version. This is fast, but installation is no longer addressed by an exact version and reproducibility and history are lost.
3. Treat proposals as derived and short-lived, and create a durable object through a single action: user confirmation.

## Decision

Option 3 is accepted.

**Search and recommendation are different modes.** Direct search remains a normal registry operation. A recommendation session is a separate flow: context snapshot, eligible candidates, one or more composition proposals, and confirmation.

**The user's agent decides how many proposals to show.** `ai_stp` returns candidates, mechanical constraints, trust lines, compatibility, and reasons; the result size limit remains the policy limit under `REQ-620`. The product does not impose any proposal as the only correct one and does not invoke a model.

**A proposal is short-lived.** Showing proposals creates no version, target, `entity`, revision, or synchronizable registry object. The exact snapshot is stored in a local session row because confirmation runs in a separate CLI process and must detect staleness. Cancellation records only an idempotent terminal outcome for that row; it creates no domain object and does not change the target.

**Confirmation atomically fixes exactly one object.** Explicit confirmation of one proposal freezes its exact graph as a new private `SetupVersion` for the selected harness, records `RecommendationTrace`, and pins the version as active for the project and harness pair under `REQ-514`. No confirmation means no `SetupVersion`.

*Clarification dated 2026-08-05: pinning in this decision means the selected version for the pair; it becomes installed after provider `verified`, and the interval between them is the `pending_install` state, not drift. The exact boundary is defined in `docs/contracts/selection-proposal.md`.*

**Confirmation is bound to exact input.** A change to a candidate hash, context passport revisions, or policy version makes the proposal stale; confirmation of a stale proposal is rejected with a typed error and requires a new session. Repeated confirmation of the same proposal idempotently returns the same version.

## Consequences

- `SPEC-006` receives requirements for proposal ephemerality, atomic confirmation, and staleness;
- `SPEC-011` declares recommendation-session and confirmation actions in machine help;
- the machine boundary for proposal and confirmation belongs to `docs/contracts/selection-proposal.md`;
- user journeys and the architecture overview show confirmation as the boundary between recommendation and installation;
- the domain model marks a proposal as a derived short-lived object.

## Reconsideration conditions

This decision will be reconsidered if a demonstrated need appears for durable proposal drafts—in that case they will become a separate entity with their own lifecycle, not versions—or if confirmation idempotency proves insufficient for multi-device scenarios.
