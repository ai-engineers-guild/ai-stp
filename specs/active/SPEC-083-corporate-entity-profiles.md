---
description: "SPEC-083: Persistent tenant presentation and independent technology ownership."
last_verified: "2026-09-13"
---

# SPEC-083: Corporate entity profiles

## Purpose

Provide persistent tenant-scoped presentation and independent technology ownership
for Corporate Hub teams, projects, employees and technologies. This specification
defines the stored fields, edit authority, HTTP behavior, revision/idempotency
semantics, asset safety, compatibility, and executable acceptance oracles.

## Scope

Corporate Hub goals 9 and 11 add tenant presentation to existing teams, projects,
employees and technologies. Existing directory and overview projections remain
independent. Catalog ownership is outside this specification.

## Terms

- `Tenant entity` — an existing team, project, employee membership, or technology
  identified by its incumbent typed stable ID inside one organization.
- `Entity profile` — tenant-local presentation fields and their independent
  profile revision; it does not replace the entity's canonical name, lifecycle,
  object revision, or global account profile.
- `Presentation editor` — an organization administrator, active team lead, or,
  for one technology presentation only, its active owner.
- `Technology owner` — an optional active employee responsible for a technology;
  this ownership is independent of responsible teams, authorship, and access
  administration.
- `Processed asset` — a ready avatar or gallery object produced by the incumbent
  media pipeline and delivered through its existing media route.

## Requirements

- `REQ-8301`: Store Markdown description, optional processed avatar asset, at most
  eight labeled HTTPS links and five incumbent presentation media items on each
  tenant entity. Profile content has an independent nonnegative revision, initially
  zero. Editing it preserves identity, legacy name, lifecycle and object revision.
  Empty stored profiles fall back to incumbent descriptions. Employee presentation
  never modifies global account profiles.
- `REQ-8302`: Active tenant administrators with organization `member.update`
  permission and employees leading any active team in that tenant can edit all
  four profile kinds. An active technology owner can edit only their own technology
  presentation. Membership suspension and team archival revoke derived authority.
  These edit grants do not grant access administration or technology governance.
- `REQ-8303`: A technology has an independent optional owner account constrained
  to membership in the same tenant. Only administrators and active team leads
  assign or clear ownership; a new owner must be an active tenant employee.
  Assignment uses the profile revision, never changes responsible leads or authors,
  and does not create role bindings. Reads omit owner IDs when employees are unreadable.
- `REQ-8304`: Additive GET/PUT `entity-profiles/{subject_kind}/{subject_id}` routes
  validate incumbent typed IDs for team/project/employee/technology. GET returns
  name, fields, profile revision, processed avatar URL and current edit capability.
  PUT replaces fields using an exact profile revision, current authorization revision
  and durable idempotency key. Owner PUT `technologies/{technology_id}/owner` uses
  the same checks. These request revisions are the mutation precondition; these
  routes do not use an `If-Match` header. Replays reauthorize before returning the
  durable response.
- `REQ-8305`: New avatars must be ready assets belonging to the editor. Existing
  avatars and media may be retained by another authorized editor. New storage media
  references must belong to the editor; unsafe arbitrary delivery paths are rejected.
  Reuse incumbent avatar processing, presentation media validation, video
  normalization and processed asset delivery. POST `profiles/{kind}/{id}/media`
  accepts raw bytes with purpose `avatar` or `media`, exact profile revision,
  authorization revision and `Idempotency-Key`. It returns a ready asset reference
  without attaching it or changing the profile revision. Profile PUT attaches it.
  Gallery assets reuse the incumbent processed upload record and delivery route.

## States and errors

An entity without stored presentation fields reads with profile revision `0` and
the incumbent description fallback. A successful profile or ownership write
increments only the profile revision; canonical identity, legacy name, lifecycle,
object revision and responsible-team relations remain unchanged. A stale
`expected_revision` is a precondition failure and leaves the row, assets and
receipt unchanged.

An owner is either null or an active same-tenant employee. An unreadable or
suspended owner is omitted from the response rather than represented by a raw ID.
An upload is a ready, editor-owned asset reference with no profile attachment;
attachment occurs only in a later profile PUT. Repeating a mutation with the same
idempotency key reauthorizes and returns its durable response; changing the effect
under that key is rejected.

Typed identity/content violations are validation failures. Missing, foreign,
inactive, or unauthorized entities and assets are denied without enumeration.
Unsafe URLs, unsupported media, invalid sizes and malformed upload bytes are
rejected before a profile mutation. Audit and error responses contain safe metadata
and the request correlation ID, not source bytes or credentials.

## Security and privacy

Every read and mutation is scoped to the explicit organization and first verifies
active membership and the current tenant policy. Administrators and active team
leads may edit tenant presentation; a technology owner may edit only that
technology's presentation and cannot assign ownership. Ownership assignment is
restricted to administrators and active team leads and never creates a role
binding, grant, registry decision, or provider credential.

Employee presentation is stored on the organization membership and never changes
the global account profile. Avatar and gallery references must be ready assets
owned by the editor unless they are already retained by the current profile.
Delivery paths are generated by the incumbent stores; arbitrary object paths and
cross-tenant assets are not accepted. Safe before/after audit records retain the
actor, target, revision, operation and correlation without secrets or private
payloads.

## Compatibility and migration

Migration `0074_corporate_entity_profiles` is additive: it retains incumbent
entity IDs, names, lifecycle, object revisions, memberships and account profiles,
and adds profile content, profile revisions and technology owner references.
The new `/entity-profiles/...`, `/technologies/.../owner` and
`/profiles/.../media` routes are additive. Profile writes carry their typed
revision fields in the request model; they do not require an `If-Match` header.
Uploads reuse the existing processed avatar record and `/v1/media/avatars/...`
delivery route, so rollback can disable the routes without deleting stored assets,
profiles, owners, receipts or audits. Catalog operational ownership remains owned
by SPEC-082/ADR-0189.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8301` | `tests/unit/test_corporate_entity_profiles.py::test_profile_contracts_validate_identity_and_safe_content` validates typed subjects and safe fields; `::test_revision_guard_and_persistent_write` verifies independent profile revision increments while the canonical object revision stays unchanged. |
| `REQ-8302` | `tests/unit/test_corporate_entity_profiles.py::test_edit_authority` covers administrator, lead, technology-owner and owner-assignment boundaries; `::test_denied_membership_never_checks_edit_grants` and `::test_lead_lookup_is_tenant_and_active_team_scoped` verify membership and active-team scoping. |
| `REQ-8303` | `tests/unit/test_corporate_entity_profiles.py::test_revision_guard_and_persistent_write` exercises the technology-owner mutation and stale revision guard; `tests/api/platform/test_corporate_directory_competence_authorization.py::test_profile_omits_suspended_technology_owner` verifies suspended owners are not disclosed. |
| `REQ-8304` | `tests/api/platform/test_corporate_directory_authorization.py::test_corporate_profile_routes_are_registered` covers the real GET/PUT/upload/owner route surface; `tests/contract/test_openapi.py::test_corporate_profile_and_ownership_mutations_use_payload_revisions` verifies idempotency and payload/query revision declarations without `If-Match`; `::test_revision_guard_and_persistent_write` covers stale writes. |
| `REQ-8305` | `tests/unit/test_corporate_entity_profiles.py::test_foreign_assets_rejected_before_mutation` rejects cross-account avatar/media references; `::test_gallery_upload_reuses_owned_avatar_delivery` verifies the incumbent namespace and delivery path; `tests/unit/platform/test_avatar_store.py::test_asset_writes_reject_unowned_or_foreign_namespaces` verifies storage ownership boundaries. |

## Validation and rollback

The acceptance oracles above cover typed identities, unsafe content, edit
authority, membership denial, optimistic revisions, idempotent route declarations,
asset ownership and incumbent delivery. Migration 0074 adds content and owner
columns without rewriting existing values. Application rollback disables the new
routes and retains profile content, owners, receipts and audit records.
