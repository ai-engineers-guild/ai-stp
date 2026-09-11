---
description: "SPEC-074: Local, personal SaaS, and corporate product modes and their compatibility matrix."
last_verified: "2026-09-09"
---

# SPEC-074: Product modes and compatibility

## Purpose

Preserve the complete local-first product while adding explicit personal SaaS
and corporate contexts whose available behavior is testable and does not depend
on deployment packaging or per-component feature flags.

## Scope

This specification owns issue #225 and the B2B-00 product-mode matrix. It defines
how a context resolves to `local`, `personal`, or `corporate`, how those modes
relate to authentication and deployment profiles, and which capability families
may appear in each mode.

It does not implement corporate users, teams, RBAC, assignments, telemetry,
invitations, SAML, or production deployment. Those capabilities remain owned by
the later B2B milestones. It does not change the MVP release boundary in
`SPEC-001`; B2B-00 is additive after that line.

## Terms

- **Product mode** — the closed context kind `local`, `personal`, or
  `corporate` from which effective capabilities are derived.
- **Access state** — anonymous or authenticated session state, independent of
  product mode.
- **Deployment profile** — the build/deployment selection such as
  `public_saas` or `self_hosted`; it is not authority.
- **Active context** — local CLI state or a remote organization resolved by the
  authoritative backend. Web does not select it.

## Requirements

- `REQ-7401`: The product mode registry contains exactly `local`, `personal`,
  and `corporate`; an unknown value is rejected rather than mapped to a default.
- `REQ-7402`: Local mode requires neither an account nor a remote organization.
  Personal mode requires an authenticated account and its personal organization.
  Corporate mode requires an authenticated account, an explicitly selected
  corporate organization, active membership, and server-side authorization.
- `REQ-7403`: Anonymous/authenticated access is represented separately from
  product mode. Anonymous public catalog reads do not create a fourth mode. An
  authenticated Web request uses the server-resolved personal SaaS context by
  default; a different backend endpoint may return its own server-owned
  context and settings. Local mode is not a Web mode.
- `REQ-7404`: `public_saas` and `self_hosted` remain deployment profiles. A
  profile may control deployment-owned content features but cannot grant,
  revoke, or imply a product capability.
- `REQ-7405`: Effective behavior is derived from the versioned capability
  projection in `SPEC-076`; no route or component maintains an independent
  local/personal/corporate feature matrix.
- `REQ-7406`: After initial setup, local mode retains every offline operation in
  `offline-capability.md`, including project indexing, local technology facts,
  local registry use, selection, compilation, installation, status, and recovery.
- `REQ-7407`: Personal mode adds account-scoped cloud sync, private objects,
  publication, grants, devices, and personal project/technology views, but never
  exposes corporate membership, team, organization-administration, assignment,
  audit, SAML, or enterprise-operation capabilities.
- `REQ-7408`: Corporate mode may expose organization, staff, team, project,
  technology, catalog-ownership, assignment, audit, telemetry, invitation, SAML,
  and enterprise-operation capabilities only when their owning specifications
  are implemented and the current server policy grants them.
- `REQ-7409`: The mode matrix is additive by capability family. Enabling a later
  corporate family does not alter local behavior or make a local action require
  an organization.
- `REQ-7410`: Changes to the active context originate from local CLI state,
  authentication, or authoritative backend configuration. Web exposes no
  context selector, does not persist a selectable mode or organization, and
  does not send client-selected context headers. A fresh backend response
  recomputes capabilities without reusing data from the previous context.
- `REQ-7411`: A client distinguishes an unsupported capability from an
  unavailable dependency, a forbidden action, an unauthenticated session, and a
  stale capability projection; none is rendered as an empty successful result.
- `REQ-7412`: Every shared route and action has a local/personal/corporate test
  row plus independent authentication and deployment-profile rows, so no test
  can pass merely because two axes currently have the same value.

## Mode matrix

| Axis | `local` | `personal` | `corporate` |
|---|---|---|---|
| Authority source | local user and local safety policy | authenticated account in personal organization | authenticated membership and scoped server policy |
| Network | optional after setup | required for cloud operations | required for organization operations |
| Ownership scope | local device/project | single-user personal organization | selected corporate organization |
| Baseline product | local project, technology facts, registry, setup lifecycle | local baseline plus personal cloud catalog and sync | shared baseline plus authorized corporate capability families |
| Corporate administration | unavailable | unavailable | capability-gated |

## States and errors

Mode resolution returns `ready`, `unauthenticated`, `context_required`,
`context_forbidden`, `capability_unavailable`, or `capability_stale` with a safe
recovery action. A missing corporate dependency is `capability_unavailable`; it
does not downgrade the context to personal mode.
Web does not render a context selection or a local-session recovery control.

## Security and privacy

Product mode is not accepted from Web as authority. For remote contexts the
server derives it from authentication, endpoint/deployment configuration,
organization membership, and policy. Local mode sends no local path, project
contents, environment value, or private passport to determine mode. Logs may
record mode and a safe context identifier but not capability-bearing session
material.

## Compatibility and migration

Add product mode and capability fields to new response versions or as optional
fields under the existing additive policy. Existing CLI, anonymous, and
authenticated paths continue to work. Web uses its configured backend URL and
the authenticated session; old Web context cookies are ignored. Deployment
profiles keep their current names and behavior. Rollback removes B2B capability
exposure while leaving local state and personal account data intact.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7401` | Schema and parser tests accept exactly the three modes and reject an unknown or empty value. |
| `REQ-7402` | API and CLI tests resolve local without auth, personal with the personal organization, and corporate only with active membership; Web never starts local mode. |
| `REQ-7403` | Anonymous catalog, authenticated personal, and authenticated corporate fixtures prove access state and mode are independent. |
| `REQ-7404` | Both web profiles run the same authorization matrix, and changing the profile never adds a capability. |
| `REQ-7405` | A drift check finds one capability owner and rejects a second per-component mode registry. |
| `REQ-7406` | The established network-disabled local E2E path passes unchanged after B2B contracts are enabled. |
| `REQ-7407` | Personal-mode API and browser tests reject every corporate-only capability and route. |
| `REQ-7408` | Corporate fixtures expose only capabilities granted by implemented owner specs and current policy. |
| `REQ-7409` | Enabling a corporate capability leaves local contract snapshots and offline tests byte-for-byte unchanged. |
| `REQ-7410` | Web requests with stale mode or organization cookies still use the configured backend and server-derived context, while API tests cover context changes without ownership or project-link mutation. |
| `REQ-7411` | Contract/browser tests render distinct unavailable, forbidden, unauthenticated, stale, and empty states. |
| `REQ-7412` | The generated mode matrix covers every shared route/action across mode, auth state, and deployment profile. |
