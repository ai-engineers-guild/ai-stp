---
description: "Operate per-tenant GitLab discovery and retained provider observations."
last_verified: "2026-09-22"
---

# GitLab discovery

Configure `AI_STP_GITLAB_CONNECTIONS` as the deployment's secret setting, keyed
by organization ID. Each connection has a GitLab `base_url`, its exact
`allowed_hosts`, and a credential supplied by the deployment secret store. Use
`https://gitlab.com` or an explicitly approved self-hosted HTTPS hostname. Keep
the connection out of source control, logs, passports, and API requests.

An authorized operator lists repositories, registers an immutable numeric GitLab
repository ID, then refreshes the resulting provider observation as needed. The
observation includes the current namespace, URL, default branch, and head
revision. A rename changes these mutable fields without changing the provider
project ID. To make the repository part of a corporate project, follow the
explicit project creation and SPEC-078 linking flow; discovery does not infer it.
After an explicit link, register/refresh updates the linked project's repository
activity and source availability; an unlinked observation cannot update it.
Read the corporate project to inspect its bounded linked repository metadata.
After linking, publish an immutable technology mapping snapshot and call the
language enrichment route with the current project revision and a stable scan ID.
Inspect the proposed facts and review them through the existing technology
decision flow before they appear as accepted landscape facts.

If GitLab returns inaccessible or unavailable, retain the previous observation
and inspect the deployment connection and upstream access. Retry refresh with a
new idempotency key and the current identity revision after access is restored.
Disconnect clears the observation's installation marker and blocks refresh while
retaining identity and links. Re-enable through an explicit operator decision.

## Read-only source connector (ADR-0224)

The same `AI_STP_GITLAB_CONNECTIONS` entries may carry the instance's OAuth
application: `oauth_client_id` and `oauth_client_secret`. Register the
application on the GitLab instance (Admin → Applications or the group's
Applications) with redirect URI
`{api callback base}/v1/connectors/gitlab/callback` and the `read_api` and
`api` scopes. Add `AI_STP_GITLAB_CONNECTOR_ENCRYPTION_KEY` — URL-safe base64 of
exactly 32 random bytes — to encrypt stored user grants. A connection without
OAuth credentials answers `connector_not_configured` and keeps discovery only.

Members of the organization then connect under
`/v1/corporate/organizations/{id}/gitlab/*`. Connect requires the account's
linked `gitlab` sign-in identity on the same instance host, and the grant can
only ever read: project listing, repository metadata, languages, commit lookup
and the source archive. Source preparation produces an immutable
`gitlab_source_binding` that a publication plan references through
`gitlab_source_binding_id` exactly like the GitHub flow — the plan binds to at
most one source. Disconnect clears local grant state; nothing writes back to
GitLab.

## Administration consent and action plans (ADR-0225)

A second consent purpose, `administration`, asks the GitLab OAuth application
for the `api` scope and stores a separate encrypted grant. Through it the
organization can change repository visibility, grant or revoke collaborator
access, and create repositories — never directly. Every mutation is a durable
action plan the operator confirms with its exact hash; visibility changes
additionally require typing the full `path_with_namespace`. The plan expires
after about ten minutes and reconciles the live repository identity
(namespace, path, visibility) before the write; a drifted repository or a
re-authorized connector aborts with a typed error, and an already-applied
plan replays its recorded result idempotently.

Each capability is an organization permission —
`connector.gitlab.{use,read,write,create,visibility,access}` (and the
`connector.github.*` mirror). Administrators grant them on the roles screen;
the corporate settings page lists both providers with their current grants.
`superadmin` holds all of them, `lead`/`staff` hold `use` and `read` only.
GitLab administration never appears on SaaS: without
`AI_STP_GITLAB_CONNECTIONS` every route is unreachable.

## Provider kill-switches (ADR-0225)

`AI_STP_AUTH_DISABLED_PROVIDERS` (comma-separated provider names) closes a
provider's sign-in, callback, identity-link and device flows for the whole
deployment; the login page already reads `AI_STP_AUTH_PROVIDERS` for its
button list. `AI_STP_GITHUB_CONNECTOR_DISABLED=true` turns the GitHub
connector off — every connector route answers `connector_not_configured` and
the web UI shows the unavailable state rather than the connection controls.

## Asynchronous technology research

`POST …/gitlab/observations/{provider_project_id}/projects/{project_id}/
research` queues a `gitlab_technology_scan` job instead of scanning inline.
The caller passes the current policy revision, expected project revision, a
stable scan ID and the immutable mapping version; the job payload carries no
credentials. The worker revalidates the persisted tenant envelope
(organization, permission `technology.scan.publish`, project scope) before
fetching anything, then re-checks the live head revision against the stored
observation and merges facts through the same path the synchronous enrich
uses. A stale observation or revoked capability dead-letters the job; a rate
limit retries.

On application rollback, stop discovery routes. Existing provider identity rows
remain readable through the project identity flow; migration 0091 can be reversed
only if the retained branch/revision metadata is no longer needed.
