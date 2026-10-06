---
description: "The GitLab connector binds expiring user grants to accounts for read-only source preparation; it can never mutate a repository."
last_verified: "2026-10-05"
---

# ADR-0224: GitLab source connector is account-bound and read-only

Status: accepted. Implemented in `ai_stp_platform.gitlab_*` and
`ai_stp_api.slices.gitlab_connector`.

## Context

Corporate on-premise deployments need the same publication-source flow the
GitHub connector provides (ADR-0190 family): a user consents to repository
reads, the platform prepares an exact snapshot, and a publication plan binds
to it. GitLab Self-Managed has no installation model like GitHub Apps; the
equivalent is an OAuth application registered on the instance issuing
expiring user grants (`authorization_code` + `refresh_token`, ~2h access
tokens, `read_api` scope).

Two constraints shape the design. The deployment may run several GitLab
connections keyed by organization (`AI_STP_GITLAB_CONNECTIONS` already
exists for operator discovery), so a grant must record which instance it
belongs to. And the connector must not be able to change anything in
GitLab — no writes, no visibility changes, no invitations — while the
GitHub connector's administration purpose stays GitHub-only.

## Options

- Reuse the GitHub connector's shape verbatim: installation ids, scoped
  tokens, action plans. GitLab has no installations and the read-only
  constraint removes the mutation surface entirely — the model would carry
  dead fields.
- Operator PAT for everything. Simpler, but one secret reading every
  repository defeats per-account consent and identity matching; a PAT is
  also typically non-expiring.
- Per-account OAuth grants on a per-organization connection, mirrored on
  the GitHub connector's authority model: encrypted grant storage, live
  membership re-checks, immutable source bindings. Chosen.

## Decision

`AI_STP_GITLAB_CONNECTIONS` entries gain `oauth_client_id` /
`oauth_client_secret`; `AI_STP_GITLAB_CONNECTOR_ENCRYPTION_KEY` encrypts
stored tokens (AES-GCM, URL-safe base64 of 32 bytes). A connection without
OAuth credentials keeps operator discovery only; the connector reports
`connector_not_configured`.

Connect, callback, status, disconnect, and source preparation live under
`/v1/corporate/organizations/{id}/gitlab/*` plus
`/v1/connectors/gitlab/callback`, each gated by corporate membership. A
connect requires a linked `gitlab` `OAuthIdentity` whose host-qualified
subject (ADR-0223) matches the grant's `user` lookup, so the connector
token can never be bound to a different GitLab account than the one that
signed in.

Grants request `read_api` only. `gitlab_connector.gitlab_subject` stores
`{host}:{user_id}`; `gitlab_authorization_flow` is a one-use state bound to
the platform session; `gitlab_source_binding` records the immutable
coordinates (`gitlab_base_url`, `project_id`, `namespace_id`,
`path_with_namespace`, `commit`, `subpath`) beside the canonical artifact
digest, size and inventory. Access tokens are refreshed transparently under
a row lock; a revoked grant flips to `reauthorization_required` and both
ciphertexts are dropped.

`publication_plan.gitlab_source_binding_id` is mutually exclusive with
`source_binding_id` (contract-enforced). Plan validation, confirmation and
public promotion dispatch on whichever binding is present; public
provenance is re-verified anonymously — a private grant never participates
in a public read. The GitLab API surface reachable from the client is
closed by regex to metadata, languages, commit lookup and archive download
plus the `/oauth/token` identity endpoint; there is no mutation path, and
no action-plan endpoint exists.

## Consequences

- GitLab subjects reuse the ADR-0223 `{issuer_host}:{sub}` format, so a
  connector grant on instance A cannot satisfy an identity linked on
  instance B even when both report user id `7`.
- `read_api` covers project listing and archive download; `read_repository`
  is redundant and not requested.
- Token ciphertext AAD binds `account_id`, `gitlab_base_url`, `purpose` and
  token kind; a ciphertext moved between accounts, instances or token kinds
  fails authentication.
- Connector rows are account-owned; the binding's `organization_id` carries
  the account's personal organization like every other account-scoped row,
  while `connection_organization_id` records which corporate connection
  issued the grant. `account_id` stays the access boundary.
- Disconnect clears local grant state only; nothing calls back into GitLab.

## Revisit conditions

- GitLab repository administration (visibility, members) ships — that is a
  separate consent and mutation surface, modeled on the GitHub
  administration purpose, not an extension of this read-only connector.
- A deployment needs source binds from several GitLab instances for one
  account — the connector table is already keyed on `(account_id,
  gitlab_base_url, purpose)`, so only the connection configuration needs to
  grow.
