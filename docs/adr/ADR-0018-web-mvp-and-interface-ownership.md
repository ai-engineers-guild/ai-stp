---
description: "Decision to restore account management to the web MVP while retaining CLI ownership of creation."
last_verified: "2026-08-04"
---

# ADR-0018: Web MVP and interface ownership

Status: accepted.

## Context

The web was reduced to a landing page, sign-in, search, and public cards. The rationale was that every function duplicated on the web doubles the authorization surface, and while the agent remains the only working client, that cost is not justified. Profiles, devices, owned objects, publication, and permissions were moved to the CLI.

Practice showed that the reduction went too far. Some operations do not duplicate agent work: they manage the user's own account. A public profile, privacy, a device list and revocation, publication state, and granting permissions to another person are actions of the account owner, not setup-building steps. Requiring the CLI for them means that a user cannot revoke a stolen device or close a public profile from another machine.

At the same time, the original concern remains valid: if the web gains its own implementation of the rules for creating passports, indexing, selection, building, and installation, a second business-logic implementation with its own errors will emerge.

## Options

1. Retain the minimal web. This preserves a small surface but leaves account and security management available only from a configured device.
2. Build a full-featured web interface with all CLI capabilities. This meets the need but creates a second implementation of business rules and doubles the validation cost.
3. Divide responsibility by ownership rather than scope: the web owns the account and publication; the CLI and agent own creation and installation.

## Decision

Option 3 is accepted.

**The web MVP includes:**

- a landing page and installation command;
- sign-in through Google and GitHub;
- public search, cards for objects and versions, passports, compatibility, and a check summary;
- public profiles;
- the account profile, public projection, and privacy settings;
- devices, their state, and revocation;
- owned drafts, objects, and versions;
- publication and its state;
- synchronization state;
- granting and revoking permissions by account identifier and verified email;
- minimal administrative actions with mandatory auditing.

**The CLI and agent remain canonical** for creating and changing passports, indexing a project, selection, building, checks, and installation. The web displays the results of these operations but does not perform them.

**The web has no second business logic.** The web and CLI invoke the same application scenario and the same API. A web route unavailable to the CLI is permitted only for a distinct security reason, and that reason is recorded.

**A full web editor remains outside the MVP.** Browser-based setup building, social features, payments, an enterprise interface, and a telemetry panel are not included in the MVP.

## Consequences

- `docs/product/web-scope.md` describes both groups and the ownership boundary instead of a deferred list;
- `SPEC-010` expands the web-interface requirement and gains a separate requirement prohibiting a second implementation of the rules;
- `docs/engineering/implementation-roadmap.md` changes the contents of the minimal-web phase;
- the permission matrix covers the web and CLI as two clients of one API;
- a contract check proves that writing a passport is available only through the CLI and API scenario, not through a separate web handler.

## Reconsideration conditions

The decision shall be reconsidered if web account management begins to require rules absent from the CLI API, or if a proven need emerges to create and build setups in the browser.
