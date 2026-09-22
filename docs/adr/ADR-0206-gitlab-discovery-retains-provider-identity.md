---
description: "GitLab discovery records provider observations on canonical project identities without creating project links."
last_verified: "2026-09-22"
---

# ADR-0206: GitLab discovery retains provider identity

Status: accepted. Uses ADR-0182 identities and SPEC-078's explicit linking boundary.

## Context

GitLab returns an immutable numeric repository ID along with mutable namespace,
path, URL, default branch, and head revision. A rename must update the observation
without matching projects by name or URL. A failed read must not delete a project
or sever a link.

## Decision

The GitLab adapter reads only bounded project metadata, language shares, and the
default branch head. The API accepts one operator-configured HTTPS host per tenant;
the host must be GitLab.com or explicitly allowlisted. Credentials remain in
runtime settings and never cross the discovery request or response contract.

`ProjectIdentity(namespace="provider")` owns the observation. Its
`external_key` binds the configured host and immutable repository ID. The
existing provider namespace and identity fields retain namespace ID, current URL,
and observed name; two additive columns retain default branch and observed
revision. Register and refresh never create or alter `ProjectLink`. Connecting a
provider observation to a corporate project still uses the explicit SPEC-078
link plan.

Register, refresh, and disconnect use tenant authorization, a checked capability
revision, expected identity revision, idempotency receipt, and audit event.
Disconnect clears the provider installation marker and preserves identity,
metadata, history, and any existing project link. A deleted, private, or otherwise
inaccessible upstream repository rejects refresh without changing the retained
observation. Register with the current identity revision reconnects the same
immutable observation.

Language enrichment requires an existing linked provider/remote project pair and
an immutable tenant mapping version. It reuses the canonical technology scan
publication service with a distinct GitLab scope. Forge language evidence includes
the observed commit and detector/mapping versions; the resulting facts remain
`proposed` until the owner reviews them. Unmapped languages are omitted rather
than creating technology identities.

## Consequences

GitLab discovery can be enabled per tenant without exposing a credential in API
payloads. A renamed repository keeps its identity. A newly observed repository
does not appear as a corporate project until an explicit project and link decision
is made. The configured host and credential remain an operator responsibility.
