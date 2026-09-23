---
description: "GitLab discovery routes and their provider identity boundary."
last_verified: "2026-09-22"
---

# GitLab discovery contract

`SPEC-090` and `ADR-0206` own this `/v1/corporate/organizations/{organization_id}`
surface:

| Method and path | Permission | Result |
|---|---|---|
| `GET /gitlab/repositories?limit=100` | `project.list` | Bounded remote repository list with any retained provider identity. |
| `POST /gitlab/repositories/{repository_id}` | `project.create` | Register one immutable GitLab repository ID as a provider observation. |
| `POST /gitlab/observations/{provider_project_id}/refresh` | `project.update` | Refresh the same immutable repository ID, including rename and head revision. |
| `POST /gitlab/observations/{provider_project_id}/disconnect` | `project.update` | Stop refresh and retain the observation and any explicit link. |
| `POST /gitlab/observations/{provider_project_id}/projects/{project_id}/enrich` | `technology.scan.publish` plus canonical fact permissions | Publish mapped language evidence as proposed facts for an explicitly linked project. |

Mutations require `authorization_revision`, `expected_revision`, and
`idempotency_key`. New registration expects revision zero; reconnecting a
disconnected observation expects its current revision. Refresh and disconnect
also expect the current provider identity revision. The response carries exact GitLab
namespace and repository IDs, repository URL, default branch, observed revision,
observation time, stable provider project ID, and connection state. Requests do not
carry credentials or source content. The JSON Schemas are generated under
`schemas/v1/gitlab-*`.

Enrichment adds a stable `scan_id` and immutable `mapping_version` to the mutation
request. It requires the provider observation's retained head revision to match
GitLab's current default branch head. The result is the existing
`TechnologyScanResult`; unmapped language names are omitted. Accepted technology
facts remain governed by the existing review endpoints.

The provider observation is not a corporate project. Create or select the remote
project and use the explicit SPEC-078 link plan when the two identities should be
related. The authorized project read includes the linked repository's retained
namespace, URL, default branch, and observed revision, plus source availability
and activity. It returns at most 256 linked GitLab identities. Inaccessible
upstream repositories do not erase prior observations.
