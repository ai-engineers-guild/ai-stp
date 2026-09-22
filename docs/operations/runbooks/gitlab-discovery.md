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
After linking, publish an immutable technology mapping snapshot and call the
language enrichment route with the current project revision and a stable scan ID.
Inspect the proposed facts and review them through the existing technology
decision flow before they appear as accepted landscape facts.

If GitLab returns inaccessible or unavailable, retain the previous observation
and inspect the deployment connection and upstream access. Retry refresh with a
new idempotency key and the current identity revision after access is restored.
Disconnect clears the observation's installation marker and blocks refresh while
retaining identity and links. Re-enable through an explicit operator decision.

On application rollback, stop discovery routes. Existing provider identity rows
remain readable through the project identity flow; migration 0091 can be reversed
only if the retained branch/revision metadata is no longer needed.
