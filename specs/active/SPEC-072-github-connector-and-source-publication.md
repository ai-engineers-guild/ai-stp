---
description: "SPEC-072: Selected GitHub App source access and separately confirmed repository management."
last_verified: "2026-09-07"
---

# SPEC-072: GitHub Connector and source publication

## Purpose

An authenticated owner connects selected GitHub repositories, publishes a component
from an exact snapshot and separately decides whether to invite a collaborator or
expose a repository. GitHub sign-in continues to establish identity only.

## Scope

Issues [181](https://github.com/ai-engineers-guild/ai-stp/issues/181),
[182](https://github.com/ai-engineers-guild/ai-stp/issues/182),
[183](https://github.com/ai-engineers-guild/ai-stp/issues/183),
[184](https://github.com/ai-engineers-guild/ai-stp/issues/184),
[185](https://github.com/ai-engineers-guild/ai-stp/issues/185) and
[186](https://github.com/ai-engineers-guild/ai-stp/issues/186).
Artifact authorization remains with SPEC-026 and SPEC-071. Client-side artifact
encryption and general RBAC are separate work.

## Terms

A connector is one account's explicit GitHub App user authorization. An installation
scope is the live intersection of that user's access and the App's selected
repositories. A source binding is a server-only immutable association of repository
identity, exact commit, subpath and canonical artifact with a publication.
An administrative connector is separately consented authority for repository
administration; a component grant never confers that authority.

## Requirements

- `REQ-7201`: Normal GitHub sign-in never authorizes private source access. A
  separate authenticated, CSRF-protected connect action starts an account/session-
  bound, expiring, one-use OAuth flow. Callback replay, another account, a missing
  session and a mismatched GitHub identity refuse.
- `REQ-7202`: Ordinary connection uses a public GitHub App with metadata and
  contents read only. Personal and organization installations support selected
  repositories. Repository administration uses a separate explicit consent and
  App registration, so ordinary connection never requests administration write.
- `REQ-7203`: Expiring user tokens are stored encrypted on the server with a
  dedicated deployment key and account/purpose binding. Tokens, refresh material
  and App credentials never enter browser storage, passports, audit payloads,
  public responses or logs. Expired authorization requires reconnection.
- `REQ-7204`: Repository reads recheck live user installation membership, selected
  repository identity and effective contents permission. Missing, expired,
  revoked, suspended, unselected or insufficient access fails closed; cached
  metadata is not authority. Organization approval remains an explicit pending
  result, not a successful connection.
- `REQ-7205`: Disconnect removes usable local token material and makes subsequent
  source access fail closed. The user can separately revoke the App on GitHub.
  Disconnecting source access does not revoke existing ai-stp artifact grants.
- `REQ-7206`: Source preparation accepts only a selected repository ID, full commit
  SHA and bounded component subpath. It verifies the returned repository and exact
  commit and downloads through official GitHub API/archive hosts, stripping
  authorization on cross-host redirects. Ref substitution, unsafe redirects,
  ambiguous archive members and traversal refuse.
- `REQ-7207`: Preparation reuses the canonical component-tree packer and bounded
  source extractor. GitHub archives contain tracked snapshot files, including
  tracked files matched by ignore patterns; ignored untracked working-tree files
  cannot enter that snapshot. Links, special files, secret-like paths, invalid
  text, excessive size and empty/missing roots refuse. Inventory is sorted and
  binds the exact packed bytes and digest.
- `REQ-7208`: Private repository coordinates remain only in the server-only source
  binding. A privately sourced passport has no GitHub source coordinates. The
  binding records observed source visibility, publisher, installation, immutable
  repository identity, commit, subpath, artifact digest/size and passport digest.
  The server accepts a missing component source only with that verified binding.
- `REQ-7209`: Connector publication retains ordinary plan, artifact, safety and
  owner checks. Preparation grants no public exposure. Plan confirmation rechecks
  the connector and selected repository; identical retries retain the binding and
  bytes. Public publication from a currently private source refuses.
- `REQ-7210`: Owner component promotion uses the SPEC-071 visibility plan and an
  explicit confirmation. This MVP implements only private to public, including
  harmless repeated public requests. It preserves version, passport, provenance,
  artifact identity, digest, bytes and bucket location.
- `REQ-7211`: Promotion rechecks current owner/device, digest, lifecycle, public
  publisher profile, license, tags, artifact integrity, mandatory validation and
  public source eligibility before updating any public projection. Bound GitHub
  sources are re-resolved anonymously at their exact commit/subpath and compared
  with stored canonical bytes. Private or unavailable sources refuse. A bound
  source may satisfy provenance without rewriting the historical passport.
- `REQ-7212`: A promoted version is served with explicit
  `distribution_visibility=public`. Catalog search, detail, exact version and
  artifact reads observe the same distribution policy. Existing owner/grantee
  access remains valid. No object-store copy is performed.
- `REQ-7213`: Invitation plans require a separately connected administrative App,
  selected repository, current owner/admin authority and exact recipient/role.
  Personal private repositories warn that collaborator access includes write;
  read-only is available only where the organization supports it. Confirmation
  is explicit and server-enforced. Component grant creation sends no invitation.
  An authenticated action-status read refreshes pending/accepted invitation state
  without sending an invitation; revoked or missing invitations are not reported
  as pending. The read rechecks selected repository and owner/admin authority.
- `REQ-7214`: Repository-public plans bind immutable repository ID, owner ID,
  full name, prior visibility, actor, device, expiry and digest. Confirmation
  requires the exact full repository name and a separate affirmative confirmation
  after warning that the entire repository and history become public. The server
  rechecks scope, current admin authority, identity and visibility immediately
  before mutation. GitHub organization policy refusals produce no local success.
- `REQ-7215`: Repository actions are durable and idempotent. Concurrent confirmation
  is serialized. A lost response leaves a reconcilable result; retry reads current
  GitHub invitation/visibility before another mutation. An already-public target
  is harmless. Expired unknown plans may reconcile an observed effect but cannot
  issue a new mutation. Stale names, ownership, scope and request hashes refuse.
- `REQ-7216`: Connector lifecycle, repository actions and failures produce audit
  records with actor, opaque target identity, outcome and timestamp, without
  private source coordinates or credentials. GitHub 401/403/404/422/429 and
  transport failures map to stable, safe, actionable platform errors.
- `REQ-7217`: Account and owner interfaces expose connect, approval/status,
  selected repositories, disconnect, source publication, component promotion and
  separately confirmed repository actions in English and Russian. Keyboard,
  narrow-screen, busy, failure and retry states remain usable. The CLI uses the
  same source/publication authority and never accepts a GitHub token as a grant.
- `REQ-7218`: Readiness distinguishes local tests from live personal/organization
  installation evidence. Deployment config, callbacks, permissions, credential
  rotation, rollback and the acceptance matrix are documented. Unconfigured Apps
  are unavailable, never replaced with a global token or ordinary OAuth login.

## States and errors

Connector states are `disconnected`, `pending_approval`, `connected` and
`reauthorization_required`. Pending requests can be completed after organization
approval; disconnect clears authority from every state. Expiration or live denial
requires reauthorization. Repository plans are `planned`, `applied`, `failed` or
`unknown`; unknown effects require reconciliation before retry.

```mermaid
stateDiagram-v2
    [*] --> disconnected
    disconnected --> pending_approval: installation requested
    disconnected --> connected: authorized selected installation
    pending_approval --> connected: approval and authorization
    connected --> reauthorization_required: expiry or revocation
    reauthorization_required --> connected: fresh authorization
    connected --> disconnected: disconnect
    pending_approval --> disconnected: disconnect
    reauthorization_required --> disconnected: disconnect
```

Existing platform validation, permission, precondition, dependency and rate-limit
errors carry safe reason identifiers. No raw upstream response enters an error.
Visibility-plan states remain owned by SPEC-071.

## Security and privacy

Authorization checks precede source or object-store reads. The server chooses
GitHub hosts and token audience. No arbitrary URL or pasted token is a connector.
An App authorization is bound to the same linked GitHub subject as the signed-in
account. Repository management never follows implicitly from source publication,
component promotion or an ai-stp grant. Actual repository exposure and invitation
each require the user's specific final confirmation.

## Compatibility and migration

Add connector, source-binding and operation-plan tables without rewriting existing
passports or object locations. Existing public source resolution remains anonymous
by default and refuses private sources without a scoped connector. Existing
visibility wire models are reused. Missing-source private components are accepted
only through the source-bound path. Deploy additive migrations before enabling
the App settings; disabling those settings blocks new connector operations without
removing published artifacts. Rollback retains the new tables and immutable bytes.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-7201` | Login does not connect; account/session/state mismatch and callback replay refuse. |
| `REQ-7202` | Reader installation has no administration permission; management requires separate consent. |
| `REQ-7203` | Stored token ciphertext is account/purpose-bound; expiry refuses; response/log scans contain no token. |
| `REQ-7204` | Personal/organization selected access passes; unselected, suspended, revoked and insufficient access refuse. |
| `REQ-7205` | Disconnect prevents source reads while an existing private artifact grant still works. |
| `REQ-7206` | Exact missing/mismatched commit, unsafe subpath/redirect and ambiguous members refuse. |
| `REQ-7207` | Snapshot fixtures verify ignore semantics, sorted inventory, canonical digest, links, secrets and bounds. |
| `REQ-7208` | Private source binding survives publication; passport/public responses expose no private coordinates. |
| `REQ-7209` | Public with/without connector and private with connector pass; revoked confirmation and private public-source requests refuse. |
| `REQ-7210` | Owner promotion and replay preserve exact version/passport/artifact/location; non-owner refuses. |
| `REQ-7211` | Each failed public precondition leaves visibility and projections unchanged. |
| `REQ-7212` | Anonymous catalog/detail/version/download and owner/grantee reads agree after promotion. |
| `REQ-7213` | Owner invitation, pending/accepted replay, non-admin refusal and personal write warning are tested. |
| `REQ-7214` | Typed-name, affirmative confirmation, stale target and organization-policy refusal are enforced server-side. |
| `REQ-7215` | Concurrent and lost-response retries reconcile without duplicate invitations or unintended exposure. |
| `REQ-7216` | Upstream error matrix and audit assertions contain safe identifiers only. |
| `REQ-7217` | RU/EN component/browser tests and CLI contract tests exercise the same plans and refusal states. |
| `REQ-7218` | Repository gates pass; live installation/mutation evidence is recorded separately on exact deployed identity. |
