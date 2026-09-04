---
description: "Decision to give accounts and catalog component lines unique public identities owned independently of versions."
last_verified: "2026-09-04"
---

# ADR-0149: Public identities and owned catalog lines

Status: proposed.

## Context

An account currently has an opaque primary key but no unique public handle, and
its profile display name is revision content rather than an identity. Catalog
versions carry their owner, stable ID, and display name independently. That
shape permits two accounts to present the same name and permits a publisher to
create a previously unused version under a stable ID whose earlier versions
belong to another account.

AI STP Official needs an identity that cannot be imitated through Unicode,
case, or whitespace variants. Every component line also needs one owner and
unique canonical and localized public names while immutable historical
versions retain their original publication provenance.

## Options

1. Reserve only the literal Official strings in application validation. This
   leaves equivalent Unicode spellings and every non-Official collision open.
2. Infer line ownership from the newest catalog version. This keeps the current
   tables but permits mixed ownership and makes concurrent publication unsafe.
3. Store normalized account identity and one catalog-line identity, enforce
   uniqueness in PostgreSQL, and make versions reference the owned line.

## Decision

Option 3 is accepted.

Each account owns one immutable opaque ID, one mutable unique public handle,
and one mutable unique public display name. PostgreSQL enforces uniqueness on
their shared canonical normalization, not only on the submitted spelling.
OAuth provider names remain external metadata and do not reserve public names.
The AI STP Official ID, handle, and display name are seeded as one protected
system identity and use the same constraints.

Each component has one `catalog_identity` row keyed by `stable_id`. It names
the current owner and a globally unique normalized canonical name. Localized
RU and EN display names are stored separately and are unique within their
locale. Catalog versions reference this line and cannot select another owner.
An ownership revision is the only operation that changes line ownership.

Normalization is one versioned foundation contract: Unicode NFKC, trim,
whitespace collapse, and casefold. Handles additionally use the closed ASCII
handle grammar. Identity allocation and rename lock the normalized key and
rely on database uniqueness for the final concurrent decision.

## Consequences

- Existing conflicting account and component names must be reported and
  resolved before unique constraints become mandatory; migration never chooses
  a winner or silently renames an identity.
- Publication checks ownership at planning and again in the publishing
  transaction. A stale plan fails after an ownership revision.
- Historical passport owner fields and publication attribution are immutable;
  current ownership is read from the catalog line.
- Public and machine projections expose opaque ID, canonical name, localized
  display name, and current owner without treating a display name as identity.
- Rollback may stop new identity mutations but cannot restore the former
  ambiguous ownership model after new lines or transfers have been accepted.

## Revisit conditions

Revisit if internationalized handles are required, more public locales are
added, or a product requirement permits the same localized component display
name for independently owned lines.
