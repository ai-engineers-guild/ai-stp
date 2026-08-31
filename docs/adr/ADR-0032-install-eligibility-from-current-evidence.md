---
description: "Decision to derive version installation eligibility from the freshness of mandatory evidence without remotely disabling targets."
last_verified: "2026-08-04"
---

# ADR-0032: Installation eligibility from current evidence

Status: accepted.

## Context

The rules already described parts of the lifecycle: the `component_verified` badge is removed when evidence expires or policy tightens, the `blocked` state prohibits new installations, and an offline client uses the last known state. But no single rule connected evidence freshness to permission for a new installation: the phrase "may block new installations" left the decision to the implementation.

This creates two symmetric failures. Either a new user installs a version whose mandatory evidence expired long ago or failed, with the badge honestly removed but installation somehow allowed; or an overcautious client disables already installed targets—remote destruction of working environments that the product promised not to perform.

## Options

1. Leave blocking as a manual owner action in every case. Predictable, but between evidence expiry and manual action the catalog distributes a version it no longer verifies.
2. Automatically disable installed targets as well. Consistent, but this is remote destruction of working environments—explicitly prohibited behavior.
3. Derive installation eligibility from mandatory-evidence freshness: automatically block future installations and updates while installed targets continue working with a warning.

## Decision

Option 3 is accepted.

**Eligibility is derived, not assigned.** As soon as a version lacks current accepted `passed` evidence for any mandatory check—through expiry, revalidation failure, or policy tightening—the version simultaneously loses `component_verified`, leaves the `authoritative` trust line, and is blocked for new installations and updates. No separate manual step is required; manual `blocked` remains a separate moderator action layered over this rule.

**Installed targets keep working.** An already installed target is neither disabled nor remotely deleted; the user receives a prominent warning with the reason. The product has no remote kill switch for targets.

**Restoration uses new evidence; change uses a new version.** The author restores eligibility by obtaining a new passing `ValidationSnapshot` for the same unchanged bytes. Changed bytes require a new version; republishing under the old version number remains prohibited.

**The offline client is honest about age.** Without network access, it uses the last known eligibility state together with its validation time; the first update after connectivity returns applies current state. Stale information is not presented as current.

## Consequences

- `docs/contracts/validation-policy.md` receives an installation-eligibility section;
- `SPEC-007` receives the requirement for a single eligibility derivation; `SPEC-005` binds lifecycle states to this rule;
- user journeys describe loss of evidence as blocking new installations while the installed target keeps working;
- providers receive no remote-disable command: they only execute plans, and `ai_stp` will not create a plan for an ineligible version.

## Reconsideration conditions

This decision will be reconsidered if a vulnerability class appears for which a running installed target is unacceptable even with a warning. That case requires a separate explicit mechanism and decision, not expansion of this rule.
