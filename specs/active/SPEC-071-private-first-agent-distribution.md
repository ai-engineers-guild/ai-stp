---
description: "SPEC-071: Private-first CLI distribution with explicit owner-controlled public exposure."
last_verified: "2026-09-07"
---

# SPEC-071: Private-first agent distribution

## Purpose

An agent releases the user's component, distributes it privately, invites recipients,
acquires exact granted versions and includes them in a setup. Public exposure is a
separate explicit owner decision.

## Scope

The CLI owns exact local release, authenticated requests, digest-bound decisions,
private acquisition and account-scoped caches. The platform owner implements
authorization, private storage, invitation delivery and public projections. A client
test cannot establish support on an undeployed server.

## Terms

Distribution visibility governs server access. Immutable passports retain their
original identity. Private upload is not public catalog publication. Grant revocation
restricts future reads, not previously acquired copies.

## Requirements

- `REQ-7101`: New component versions, composed local setups and distribution plans
  default to `private`. Public distribution requires explicit selection. Existing
  immutable versions are never rewritten. The passport's historical visibility
  does not govern current server access; ADR-0169 and the private distribution
  contract own that separation.
- `REQ-7102`: Plans bind visibility, exact passport and artifact. The CLI checks
  server visibility and identity before binding bytes and confirming effects.
  Unsupported or contradictory responses refuse.
- `REQ-7103`: Explicit private reads first permit anonymous public lookup; only
  public 404 permits authenticated owner/grant lookup. Public requests contain no
  credentials. Online denial cannot become stale cached success. Offline use is
  explicit and retains acquired bytes.
- `REQ-7104`: Private caches are scoped to endpoint and account. Graph acquisition
  checks each component digest and compiles the same native bundle without claiming
  public author or component verification. `setup compose` resolves exact granted
  components through that same access path and creates a private setup.
- `REQ-7105`: Invitations and grants retain SPEC-026 authority. Only an owner can
  expose an existing object through a separate exact plan and confirmation. Upload
  and invitation acceptance do not change visibility.
- `REQ-7106`: Private preparation reuses accessible exact private and public pins;
  public preparation refuses private pins. An altered or merely cached passport
  cannot justify skipping publication of an exact participant.
- `REQ-7107`: Process and HTTP tests cover private defaults, visibility mismatch,
  wrong artifact or passport, denied and revoked access, offline possession,
  account/endpoint separation and explicit public opening.

## States and errors

SPEC-026 owns publication and grant states; `docs/contracts/private-distribution.md`
owns visibility plans. Existing typed errors distinguish authentication required,
permission denied, missing versions, integrity failures and unsupported servers.

## Security and privacy

Tokens are sent only to authenticated routes. Public discovery stays anonymous.
Source credentials are not grants and never enter passports. Native recovery
snapshots are not upload artifacts.

## Compatibility and migration

The CLI sends explicit visibility. Legacy responses decode as public only for
historical plans and cannot satisfy new private requests. The API owner must deploy
private artifact and metadata routes, visibility-bound publication and the separate
existing-object opening contract. The CLI does not emulate these with a public
endpoint or a new immutable identity.

## Acceptance criteria

| Requirement | Executable verification |
|---|---|
| `REQ-7101` | Omitted visibility yields private; explicit public remains supported. |
| `REQ-7102` | A legacy public answer to a private request uploads and confirms no bytes. |
| `REQ-7103` | Anonymous requests omit tokens; private reads need a session; denial cannot be hidden by cache. |
| `REQ-7104` | A private graph compiles and enters a new private setup; another account or endpoint cannot read its cache. |
| `REQ-7105` | Invitations preserve authority; opening requires exact explicit approval. |
| `REQ-7106` | Accessible exact pins are reused; mismatched or private public-set pins refuse. |
| `REQ-7107` | Process and transport tests pass; deployed evidence is reported separately. |
