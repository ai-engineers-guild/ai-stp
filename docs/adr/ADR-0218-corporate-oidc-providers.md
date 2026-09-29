---
description: "Corporate single sign-on runs over OIDC through named providers configured by issuer URL; authentik and keycloak are the first two."
last_verified: "2026-09-29"
---

# ADR-0218: Corporate OIDC providers are named, issuer-configured clients

Status: accepted. Implemented in `ai_stp_api.slices.auth` and
`AuthSettings` (`AI_STP_AUTH_AUTHENTIK_*`, `AI_STP_AUTH_KEYCLOAK_*`).

## Context

Corporate and self-hosted deployments authenticate against their own
identity provider, not Google or GitHub (issues #19, #220). The existing
auth slice (ADR-0041) already brokers OAuth/OIDC exchanges with PKCE,
stores `OAuthIdentity` rows keyed by provider + subject, and keeps provider
tokens out of logs and passports. The provider set was a closed enum of
two public names.

Authentik and Keycloak — and every other mainstream corporate IdP —
speak OIDC discovery. SAML support is a separate, larger stack
(assertion parsing, metadata XML, certificate rotation) and remains open
under #220; this decision covers only the OIDC path.

## Options

- A single generic `oidc` provider with a free-form issuer. Minimal, but
  a deployment could enable only one IdP and the wire name would carry no
  meaning about which IdP issued a stored identity.
- Named providers (`authentik`, `keycloak`) sharing one OIDC client
  implementation, each configured by issuer URL + client credentials.
  Adds a schema enum value per supported IdP family; no per-provider code.
- Dynamic operator-defined provider names. Would make `provider` an open
  string in the contract and weaken the closed enum everywhere it is
  validated.

## Decision

Corporate providers are named enum values (`authentik`, `keycloak`) that
share the generic OIDC registration already used for Google: discovery
against `{issuer}/.well-known/openid-configuration`, PKCE S256, and
profile extraction from `userinfo` claims (`sub`, `email`,
`email_verified`, `name`, `picture`). Each provider is enabled only when
its issuer URL, client id, and client secret are all configured. A
deployment configures zero, one, or both; a new IdP family is a schema
enum addition, not new machinery.

## Consequences

- `OAuthProvider` gains `authentik` and `keycloak`; the CLI derives its
  provider choices from the contract and needs no change.
- Subject mapping, account linking, unlinking, session, CSRF, and device
  invariants are unchanged: an authentik identity is an `OAuthIdentity`
  like any other, keyed by `sub` rather than email.
- Issuer URLs accept only `http(s)` without query or fragment. `http` is
  permitted for local IdPs; production deployments use `https`.
- Assertions, tokens, and client secrets stay out of logs by the existing
  rule; the issuer URL is deployment metadata, not a secret.
- Rollback: unset the issuer or credentials; the provider stops accepting
  logins, existing linked identities remain but cannot authenticate.

## Revisit conditions

- A deployment needs two instances of the same IdP family (two realms
  presented as distinct login choices) — then provider naming must move
  to operator-defined names and the contract enum must open.
- SAML (#220) ships — then this decision's scope note is updated and the
  shared profile/linking code is reviewed for non-OIDC claim shapes.
