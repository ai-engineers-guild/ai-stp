---
description: "ADR-0170: Separate GitHub App source authority, management consent and immutable provenance bindings."
last_verified: "2026-09-07"
---

# ADR-0170: GitHub source authority is separate from login

Status: accepted

## Context

GitHub sign-in proves a platform identity. Private source publication needs explicit
repository access, while invitations and repository exposure need administrative
authority. Requesting administration on the ordinary source App would enlarge every
new installation's permissions. Private GitHub coordinates cannot enter immutable
passports that may later be distributed publicly.

## Decision

Use a separately connected reader GitHub App with selected repositories and expiring
user access tokens. Encrypt token material server-side with a dedicated key and
account/purpose binding. Recheck the live intersection of installation scope and
user permissions before source access. Expiration requires reconnection; refresh
tokens are not retained. Sign-in credentials are never substituted.

Use a second, optional management App for explicitly consented administration. A
management action requires both selected repository access and current user admin
authority. Invitations and repository visibility changes have separate durable,
digest-bound plans and user confirmations. Unknown external outcomes are reconciled
before retry. Neither component publication nor ai-stp grants invoke those actions.

Store private source coordinates in an immutable server-only binding to the exact
publication passport and artifact. The private passport retains `source=null`; a
verified binding satisfies source provenance without introducing private coordinates
into passport bytes. Component promotion validates the bound source anonymously and
preserves the binding and passport. Distribution policy and public projection change
independently, following ADR-0169. SPEC-072 defines the one-way promotion MVP and all
acceptance requirements.

## Consequences

Operators configure separate reader and optional management App registrations and
callbacks. Ordinary installation never requests administration write. An expired
connection requires user authorization again instead of long-lived refresh material.
Disconnected users retain already granted artifact access but cannot fetch new
private source snapshots. Missing configuration remains visibly unavailable.

Private source provenance is verifiable by the platform without being public
passport content. All public eligibility checks still run before exposure; no
source privacy exception bypasses artifact integrity, safety or ownership.
