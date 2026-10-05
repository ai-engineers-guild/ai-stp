---
description: "A self-managed GitLab instance acts as a named OIDC sign-in provider; its per-instance subjects are stored host-qualified."
last_verified: "2026-10-05"
---

# ADR-0223: GitLab sign-in is a named OIDC provider with host-qualified subjects

Status: accepted. Implemented in `ai_stp_api.slices.auth` and
`AuthSettings` (`AI_STP_AUTH_GITLAB_*`).

## Context

Corporate on-premise deployments authenticate against their own GitLab
Self-Managed instance (#220 family). ADR-0218 established named OIDC
providers configured by issuer URL; GitLab Self-Managed speaks OIDC
discovery (`{issuer}/.well-known/openid-configuration`), returns
`sub`/`email`/`email_verified`/`name`/`preferred_username` claims, and
supports PKCE S256, so it fits the existing corporate provider machinery
with no new protocol code.

One difference is load-bearing: GitLab `sub` is the per-instance numeric
user id (`1`, `2`, `3`, ...), not a globally unique identifier like a
Keycloak `f:realm:uuid` subject. Two different GitLab instances — or the
same hostname re-installed — produce colliding subjects for unrelated
people, and `oauth_identity` is unique on `(provider, provider_subject)`.

## Options

- Store the raw `sub` like the other OIDC providers. Minimal, but an
  issuer re-point or a rebuilt instance silently collides identities —
  an authentication-boundary failure, not a data oddity.
- A per-instance provider value (`gitlab:{host}`) in the contract enum.
  Opens the closed provider enum to deployment-defined values, which
  ADR-0218 explicitly rejected.
- Keep `provider = "gitlab"` and qualify the stored subject as
  `{issuer_host}:{sub}`. The enum stays closed, the unique constraint
  keeps working, and a re-pointed issuer orphans rather than collides.

## Decision

`gitlab` is a fifth named provider sharing the generic OIDC registration:
discovery against `{issuer}/.well-known/openid-configuration`, scope
`openid email profile`, PKCE S256, profile from `userinfo` claims. It is
enabled when `AI_STP_AUTH_GITLAB_ISSUER_URL`, `CLIENT_ID`, and
`CLIENT_SECRET` are all configured; the issuer validator is the same
http(s)-no-query rule as the other corporate providers.

The stored `provider_subject` is `{issuer_host}:{sub}`, where the host is
taken from the configured issuer at profile extraction. `preferred_username`
(or `nickname`) feeds `ProviderProfile.username`, so GitLab usernames reach
`oauth_identity_alias` exactly like GitHub logins do. Everything else —
account resolution, step-up link, unlink, sessions, device flow, audit —
is provider-agnostic and unchanged.

## Consequences

- The contract `OAuthProvider` literal gains `gitlab`; CLI provider choices
  derive from the contract and need no change. The web SSO surface picks it
  up through `AI_STP_AUTH_SSO_PROVIDERS` (rendered only in the
  `corporate_hub` build, so a SaaS deployment simply never configures it).
- An `oauth_identity_alias` row can now carry `provider="gitlab"`; grant
  recipient lookup by username works unchanged. Alias values longer than
  the 64-char column are skipped rather than truncated.
- Re-pointing the issuer at a different instance makes old linked
  identities unresolvable but never wrong — same rollback posture as
  ADR-0218, with collision replaced by orphaning.
- GitLab accounts without a verified primary email cannot sign in
  (`email_verified` is required), matching the existing invariant.

## Revisit conditions

- A deployment needs sign-in against two GitLab instances at once — then
  provider naming must move to operator-defined names per ADR-0218's
  revisit clause, and stored subjects already carry the host.
- A user-level GitLab connector (repository authorization beyond sign-in)
  ships — the connector token stays separate from this login identity,
  and the subject format here is the join key it must match.
