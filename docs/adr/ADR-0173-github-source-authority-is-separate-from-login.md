---
description: "ADR-0173: One GitHub App, separate management consent and immutable provenance bindings."
last_verified: "2026-09-08"
---

# ADR-0173: GitHub source authority is separate from login

Status: accepted

## Context

GitHub sign-in proves a platform identity. Private source publication needs explicit
repository access, while invitations and repository exposure need administrative
authority. Requesting administration on the ordinary source App would enlarge every
new installation's permissions. Private GitHub coordinates cannot enter immutable
passports that may later be distributed publicly.

## Decision

Use one GitHub App with selected repositories, metadata/contents read and
administration write permissions. Encrypt user access tokens server-side with a
dedicated key and account/purpose binding. Recheck the live intersection of
installation scope and user permissions before source access or administration.
Expiration requires reconnection; refresh tokens are not retained. Sign-in
credentials are never substituted.

Keep source access and administration as separate consent records even though they
use the same App registration. A management action requires selected repository
access, current user admin authority and its own durable plan plus confirmation.
Invitations and repository visibility changes are reconciled after uncertain external
outcomes before retry. Neither component publication nor ai-stp grants invoke those
actions.

Store private source coordinates in an immutable server-only binding to the exact
publication passport and artifact. The private passport retains `source=null`; a
verified binding satisfies source provenance without introducing private coordinates
into passport bytes. Component promotion validates the bound source anonymously and
preserves the binding and passport. Distribution policy and public projection change
independently, following ADR-0169. SPEC-072 defines the one-way promotion MVP and all
acceptance requirements.

## Consequences

Operators configure one App registration and callback. Its installation requests the
broader administration permission, while the product keeps ordinary source work
read-only by policy and never mutates GitHub without a separate confirmed plan. An
expired connection requires user authorization again instead of long-lived refresh material.
Disconnected users retain already granted artifact access but cannot fetch new
private source snapshots. Missing configuration remains visibly unavailable.

Private source provenance is verifiable by the platform without being public
passport content. All public eligibility checks still run before exposure; no
source privacy exception bypasses artifact integrity, safety or ownership.

GitHub's permission model is documented in
[Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app),
[Authorizing GitHub Apps](https://docs.github.com/en/apps/using-github-apps/authorizing-github-apps),
and
[Approving updated permissions](https://docs.github.com/en/apps/using-github-apps/approving-updated-permissions-for-a-github-app).
