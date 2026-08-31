---
description: "Runbook: granting and revoking author_verified."
last_verified: "2026-08-22"
---

# Author verification

## How the attribute is granted

The attribute is granted through `POST /v1/staff/author-verified`, and a single
environment variable authorizes it: `AI_STP_AUTH_ADMIN_ACCOUNT_IDS`, a comma-separated list of
account identifiers.

An empty value does **not** mean “all owners by default.” It means no one: the entire staff surface,
including applications, version lifecycle, and granting the attribute, denies access to every
account, including the operator's account. The default value is empty, so
on a new deployment the steps below are physically impossible until the variable is set.

This has an important consequence when investigating the catalog: the
`authoritative` trust line requires `author_verified`, only this surface can grant it,
and when the variable is unset every published object remains in `experimental`
regardless of who published it. If publishing works but `authoritative` is empty,
check the variable first and the object itself only afterward.

The value belongs to the deployment, not the repository: it comes from `.env.prod`
on the host; the template is `.env.prod.example`.

## Grant procedure

The attribute is granted manually by platform owners under `SPEC-007` REQ-715 through two paths: an author application or a personal invitation from the owners.

1. For an application, establish what the author owns: a GitHub account, organization, or namespace.
2. Verify ownership with evidence: log in via OAuth using the same account, or place an agreed marker in the owner's repository or profile.
3. For a personal invitation, record which platform owner vouches for the author and for which namespace.
4. Grant `author_verified` to an account identifier or verified email; there are no automated grant paths.
5. Create an `AuditEvent` with the decision-maker, rationale, and time under REQ-716.
6. Remember the attribute's boundary: verified confirms provenance, not content safety, and does not grant `component_verified` to any version.
7. Revocation applies prospectively under REQ-717: the author's objects leave `authoritative`; historical snapshots and installed targets are not rewritten.
