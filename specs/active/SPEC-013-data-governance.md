---
description: "SPEC-013: User data governance."
last_verified: "2026-08-16"
---

# SPEC-013: User data governance

## Purpose

The platform minimizes data collection, preserves a private-by-default model, makes administrative access observable, and establishes predictable access rights, export, deletion, and retention before working with real users.

## Scope

Includes the developer passport, public projection, private objects, project-index summary, administrator audit, tombstones, physical purge, and backup retention. End-to-end client-side encryption and content hidden from administrators are out of scope for the MVP.

## Terms

- `PublicProfile` — a separate object populated by the user.
- `AccessGrant` — a distinct authorization, not knowledge of an account identifier or email address.
- `GrantInvitation` — an access offer before an address is confirmed by sign-in.
- `Tombstone` — logical deletion before physical purge.
- `RetentionPolicy` — approved retention periods for primary data, audit records, and backups.

## Requirements

- `REQ-1301`: The developer passport is private; the public profile is a separate object populated only by an explicit user action.
- `REQ-1302`: An account identifier and email address do not grant access without a separate active `AccessGrant`.
- `REQ-1303`: Every read of a private object verifies ownership, a grant, or administrative authority.
- `REQ-1304`: Administrative reads and changes to verification, visibility, blocking, or grants are logged with their reason and result.
- `REQ-1305`: The MVP has no end-to-end client-side encryption; this fact is explicitly disclosed to the user.
- `REQ-1306`: The full project index and source code are not uploaded without a separate user decision.
- `REQ-1307`: Secrets, raw conversations, complete shell history, and environment values are not collected.
- `REQ-1308`: Deletion immediately revokes ordinary access and creates a tombstone pending physical purge.
- `REQ-1309`: Physical purge is idempotent, accounts for object storage and backups, and leaves a minimal audit record.
- `REQ-1310`: Retention, export, and backup-deletion policies are approved before public launch of server mode.
- `REQ-1311`: A direct address, storage key, or artifact identifier does not replace authorization checks.
- `REQ-1312`: Logs, traces, and metrics contain no raw private-object text, secret value, or optional personal data.
- `REQ-1313`: Synced device-passport revisions and their permitted summary contain no absolute user paths, environment-variable values, or secrets; source paths remain in local detector state.
- `REQ-1314`: The report payload is restricted to the allowlist in `docs/contracts/report-case.md`; the reporter's identity is visible only to moderators, the author receives a sanitized notification, and moderation logs contain no private bytes or secrets.
- `REQ-1315`: Anti-abuse for public usage counters stores no raw IP, user-agent, account/device identifier, or stable visitor identifier; dedup evidence lives for a short documented period, and only the aggregate is public.
- `REQ-1316`: Client telemetry is disabled by default; before explicit consent there are no outgoing telemetry requests, and refusal and “not yet asked” are observably indistinguishable. Consent is given by a separate command with confirmation; writing `telemetry.enabled=true` by any other route is rejected.
- `REQ-1317`: A telemetry ping is one unauthenticated HTTPS `GET` with the closed field list in `docs/contracts/cli-telemetry.md`, without a body, cookie, catalog token, or authorization. Local paths, private repositories, account, device key, email, project name, target path, environment values, and file contents are excluded; if there is no publicly nameable object, no request is sent.
- `REQ-1318`: A ping is sent only after a `verified` apply with the `install` or `update` action, one per component actually installed. Network errors, timeout, and non-2xx responses are silently swallowed: the installation result does not depend on collector availability, and no batched retry occurs.
- `REQ-1319`: An anonymous identifier is created only upon consent, stored in the local data directory outside configuration, differs from `device_id`, and is not linked to an account; refusal and disabling delete it, renewed consent creates a new one, and it is not combined with public usage counters (`REQ-1315`).

## States and errors

A private object has `active`, `shared`, `access_revoked`, `tombstoned`, `purge_pending`, and `purged` states. A grant has `active`, `expired`, and `revoked` states. An invitation has `pending`, `accepted`, `expired`, and `revoked` states and grants no access before confirmation. A purge failure remains pending and is retried idempotently. An export failure does not change the source data.

## Security and privacy

PostgreSQL and RustFS are accessible only to server components. Administrator actions use least privilege and immutable auditing. Logs are built from an allowlist of fields and sanitized. Backups do not become a bypass around access revocation and are deleted under the approved policy.

## Compatibility and migration

Changing a data class or retention period requires a policy version and migration plan. Old audit records preserve their original meaning. Physical deletion begins only after confirming that supported versions do not need the object for rollback or conflict merging.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1301` | Changing a passport does not change the public profile, and an unpopulated profile is not served as a public page. |
| `REQ-1302` | Authorization rejects access by account identifier and email address without a grant. |
| `REQ-1303` | The matrix covers the owner, grant recipient, outsider, and administrator. |
| `REQ-1304` | An audit check records every privileged read and change. |
| `REQ-1305` | The user policy and API metadata explicitly disclose operator visibility. |
| `REQ-1306` | Sync checks do not send the full index or source code without consent. |
| `REQ-1307` | Sanitization fixtures confirm the absence of prohibited data classes. |
| `REQ-1308` | A deletion request immediately blocks ordinary reads and creates a tombstone. |
| `REQ-1309` | Repeated purge is safe and deletes database and storage copies under policy. |
| `REQ-1310` | Production configuration is rejected without a versioned retention policy. |
| `REQ-1311` | A direct address or storage key returns a denial. |
| `REQ-1312` | Log, trace, and metric checks verify the field allowlist and sanitization. |
| `REQ-1313` | A device-passport fixture containing paths and environment values syncs a revision without them. |
| `REQ-1314` | The authorization matrix hides the reporter's identity from the author, and moderation-log fixtures contain no private bytes. |
| `REQ-1315` | Privacy tests confirm a keyed digest without raw IP, user-agent, account/device data, and a short dedup-evidence lifetime; only the aggregate is public. |
| `REQ-1316` | Without consent, an installation fixture produces no outgoing request; `config set telemetry.enabled=true` without consent is rejected with a typed error; refusal and `not_asked` have identical network observability. |
| `REQ-1317` | The captured request contains exactly the listed fields and none outside the list; fixtures with a local path, private repository, and environment variable either produce no request or do not expose those values. |
| `REQ-1318` | Collector failure and timeout leave the operation `verified`; `backup`, `rollback`, `remove`, and reads produce no request; a three-component setup produces three requests. |
| `REQ-1319` | Refusal and disabling delete the identifier; renewed consent creates a different one; it differs from `device_id` and does not appear in ordinary state output. |
