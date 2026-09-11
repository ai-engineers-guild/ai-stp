---
description: "Product mode is derived from server authority and remains separate from access state and deployment profile."
last_verified: "2026-09-09"
---

# ADR-0175: Product mode follows the active authority context

Status: proposed.

## Context

The product already has an offline local path, anonymous public catalog reads,
authenticated account features, and the `public_saas` and `self_hosted` web build
profiles. B2B-00 adds personal SaaS and corporate operation while requiring the
local path to remain complete and corporate behavior to stay explicit and opt-in.

Treating every route or component as an independent feature flag would create a
second authorization model. Treating deployment profiles as product modes would
make the same user's authority depend on how the web artifact was built.

## Options

1. Add a feature flag for every corporate route, action, and component. This is
   flexible but duplicates policy and permits contradictory combinations.
2. Equate `public_saas` and `self_hosted` with user-visible product modes. This
   couples deployment packaging to authorization and cannot represent personal
   and corporate contexts in one deployment.
3. Derive one closed product mode from the active authority context and project
   the resulting capabilities to clients.

## Decision

Option 3 is selected.

The closed product modes are `local`, `personal`, and `corporate`:

- `local` has no required account or server organization and retains the complete
  offline boundary established by `SPEC-001` and `offline-capability.md`;
- `personal` is an authenticated single-user cloud context represented by a
  personal organization;
- `corporate` is an explicitly selected corporate organization in which
  membership and server-side policy authorize every scoped operation.

Anonymous versus authenticated access is a separate session property. Public
catalog reading is available according to access policy and is not a fourth
product mode. `public_saas` and `self_hosted` remain deployment/build profiles;
they may include or exclude deployment-owned content features but grant no
product permission.

The active context determines a versioned capability projection. Routes and UI
consume server-owned results instead of evaluating a per-component mode matrix
or presenting a context selector. Web uses the configured SaaS/backend endpoint;
an authenticated request defaults to the personal organization unless that
authoritative endpoint resolves another context. Local remains a CLI-only mode.
Changing context through authentication or backend authority changes the
effective projection; it does not move resources, merge identities, or rewrite
local state.

## Consequences

- `SPEC-074` owns the mode matrix and observable compatibility requirements.
- Personal and corporate contexts require the organization model in `ADR-0176`.
- API and Web use the shared capability contract in `ADR-0177`; server-side
  authorization remains authoritative.
- Existing MVP exclusions remain true for the MVP release line. B2B-00 is an
  additive post-MVP contract and cannot weaken local or anonymous behavior.
- Tests must cover product mode, authentication state, deployment profile, and
  capability projection as independent axes.

## Revisit conditions

Revisit this decision if a supported product context cannot be represented by
local state or one organization, or if a deployment profile must enforce a
hard legal or physical boundary that cannot be expressed by authorization and
capabilities.
