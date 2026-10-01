---
description: "Proposed separation of corporate assignments, operational ownership, and private major-line access."
last_verified: "2026-09-29"
---

# ADR-0221: Corporate private catalog access stays a separate grant

Status: proposed. Existing assignment and private-grant rules remain binding.

## Context

`CorporateCatalogAssignment` represents distribution intent and does not
install a harness or grant access. The existing `AccessGrant` represents a
private major-line grant. The target Employee access page would expose both;
joining them by label or operational ownership would silently broaden access.

## Options

1. Treat corporate assignment or local operational owner as private access.
   This confuses distribution with the author's permission boundary.
2. Reuse `AccessGrant` with a corporate-aware issuer/context adapter and show
   assignments and private grants as separate sources.
3. Create another private grant table for corporate users. This duplicates
   lifecycle and delivery rules.

## Decision

Choose option 2. A corporate administrator may grant a private major line only
when the existing owner/delegation rules permit that exact grant. Corporate
status alone never authorizes another workspace's object. The UI names the
major line and its included versions, and does not promise future majors.
Read/use are labelled according to the enforced contract; install-only,
edit, share, visibility, transfer, and delegation are not implied.

Before returning a protected card, manifest, artifact, or closed dependency,
the server checks the current effective grant for that object and recipient.
Revocation stops future delivery; already installed local copies are outside
that guarantee. An external public object's local operational owner does not
become its upstream author or editor. Corporate assignment and grants remain
independent in APIs, UI explanation, audit, and rollback.

## Consequences

- Add tests across owner context, dependency closure, revocation, tenant
  isolation, and forged grant attempts before exposing the Web control.
- Preserve personal grants and existing major-line semantics.
- Update the owning active corporate and private-access specs from implemented
  contracts; do not restate private-grant rules in every corporate spec.

## Revisit conditions

Revisit when an enforced install-only capability exists or product policy
requires explicit access to future major lines.
