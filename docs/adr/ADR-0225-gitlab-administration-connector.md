---
description: "A second GitLab consent purpose carries repository administration through durable, confirmed action plans; connector capabilities are organization permissions and providers can be disabled outright."
last_verified: "2026-10-05"
---

# ADR-0225: GitLab administration connector, connector permissions, and provider kill-switches

Status: accepted. Implemented in `ai_stp_platform.gitlab_*`,
`ai_stp_api.slices.gitlab_connector.actions`, and
`ai_stp_platform.gitlab_research`.

## Context

ADR-0224 shipped the GitLab connector read-only. Corporate deployments also
need the repository administration the GitHub connector already provides:
visibility changes, collaborator grants and revocations, and repository
creation — plus an asynchronous technology scan over linked GitLab
projects. Two further operational requirements appeared at the same time:
an organization must be able to grant connector capabilities separately
(enable, read, write, create, visibility, access), and a deployment must be
able to remove GitHub entirely so its sign-in and connector cannot be
reached through API, CLI, or UI.

## Options

- Extend the `source` grant with a wider scope. Rejected: `read_api` and
  `api` are different consent strengths; a read token must never be
  upgradeable into a mutation token.
- One shared `connector.admin` permission. Rejected: visibility, member
  access and creation are independently risky; an organization that only
  wants source preparation must be able to withhold all of them.
- Per-purpose OAuth grants on the same connector table, per-action
  organization permissions, and durable plans mirroring the GitHub action
  surface. Chosen.

## Decision

`purpose="administration"` issues a second grant row per account and
instance with the `api` scope; the source purpose keeps `read_api`. The
grant is usable only while a `gitlab` OAuth identity with the matching
host-qualified subject remains linked to the account.

Organization permissions `connector.{github,gitlab}.{use,read,write,
create,visibility,access}` join `KNOWN_PERMISSIONS`; `superadmin` holds
all, `lead`/`staff` hold `use` and `read`. GitLab mutation routes require
the action's permission (`access`, `visibility`, or `create`) on the
organization that owns the connection configuration — the OAuth grant and
the permission check can never split across two organizations.

Mutations are durable `gitlab_action_plan` rows: request and plan hashes,
the consenting device, the connector row and its authorization revision,
the live repository identity (namespace and path) reconciled immediately
before the mutation, an idempotency key, a ~10 minute expiry, and states
`planned → applied | failed | unknown`. Visibility changes additionally
require the operator to type the exact `path_with_namespace`. The GitLab
client's mutation surface is closed by allowlist to `projects/{id}`,
`projects/{id}/members[/{user}]` and `projects`; already-satisfied
outcomes (visibility at target, member already present/absent) replay as
the recorded result instead of failing.

`AI_STP_AUTH_DISABLED_PROVIDERS` removes an OAuth provider's sign-in,
callback, linking and device flows, so GitHub (or GitLab) login can be
disabled without touching provider configuration. `GitHubConnectorSettings.disabled`
turns the GitHub connector's `enabled()` off, which closes every connector
route; the web UI renders the unavailable state instead of the connection
controls. GitLab has no SaaS surface at all — without
`AI_STP_GITLAB_CONNECTIONS` nothing is reachable.

Technology research on a linked GitLab project runs as a
`gitlab_technology_scan` queue job. The API gate is
`technology.scan.publish` at project scope; the enqueue writes the tenant
envelope and the worker revalidates it before the handler touches GitLab.
The scan reuses the synchronous enrich invariants — live head revision
against the stored observation, immutable mapping snapshot, locked link —
and merges through `merge_scan_facts`; credentials ride only the
connection configuration, never the job payload.

## Consequences

- One account may hold two GitLab grants per instance (source +
  administration); disconnecting one purpose leaves the other intact.
- GitHub and GitLab capabilities are symmetrical in the permission model,
  so organization administrators edit one grant vocabulary for both
  providers on the roles screen.
- A disabled GitHub deployment answers `unsupported oauth provider` /
  `connector_not_configured` everywhere; the connector organism and the
  sign-in surface render it unreachable rather than merely hidden.
- GitLab administration needs the OAuth application's `api` scope grant,
  not a broader platform permission; the audit trail records plan creation
  and outcome without any credential material.

## Revisit conditions

- GitLab issue/MR or pipeline writes appear — a third purpose or a scoped
  deployment token, not a widening of `administration`.
- Connector kill-switches grow per-organization rather than per-
  deployment — move from settings into the authorization policy.
