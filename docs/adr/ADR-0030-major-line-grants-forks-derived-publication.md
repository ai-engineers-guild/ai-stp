---
description: "Decision to define rights to a major line, recipient forks, derived publication, and revocation consequences."
last_verified: "2026-08-04"
---

# ADR-0030: Rights to a major line, forks, and derived publication

Status: accepted.

## Context

`ADR-0004` made major line `X` the access boundary, `ADR-0020` defined invitation transport, and `SPEC-002` defined the basic grant lifecycle. But what a recipient actually receives remained undefined: whether they receive future minor versions, may edit the original, what happens upon a fork, whether received work may be republished under their name, and what remains after revocation.

Without these rules, the implementation will inevitably decide for itself: reading will become co-authorship, a received object will become republication of someone else's work, and revocation will become either remote destruction of local installations or a meaningless action.

## Options

1. A grant to an exact version. Simple, but every minor release requires a new grant and sharing degenerates into manual version distribution.
2. A grant to the entire object without line boundaries. Convenient, but a new major line—an intentional compatibility and access boundary under `ADR-0004`—would open automatically.
3. A grant to a major line: minor versions within `X` follow the grant; a new line requires a new owner decision; reading, installation, and forking are allowed, but editing the original is not.

## Decision

Option 3 is accepted.

**The grant target is an exact object and its major line.** A grant to `X.Y` applies to the entire `X.*` line: the recipient can read and install existing and future minor versions within `X`. A new major line `X+1` is not covered and requires a new grant.

**A grant permits reading, installation, and forking.** Only the owner may edit the original: a recipient's write to another owner's object is rejected. A fork creates a new private setup with a new stable identifier and the recipient as owner; it may synchronize to the recipient's private cloud registry.

**An unchanged clone cannot be republished.** Publication of a derived setup requires a substantive change to the composition, passport, or bytes of an included component and complete validation. A derived component is published only with changed bytes or passport and with a new identity and version in the recipient's namespace.

**Public derived publication is constrained by provenance.** It is allowed only when every included byte and reference is public or belongs to the recipient and applicable licenses permit distribution. Private third-party bytes are never published unchanged in any composition.

**Revocation stops the future without destroying the past.** Revocation stops future cloud reads and receipt of minor versions. Already received bytes, local forks, and installed targets are not deleted. A rebuild requiring a now-inaccessible private dependency ends with an exact typed access error, not silent substitution.

## Consequences

- the machine boundary for grants, forks, and derived publication belongs to `docs/contracts/access-grants-and-forks.md`;
- `SPEC-002` receives requirements for the grant target, recipient actions, and revocation consequences;
- `SPEC-005` receives requirements for forks, the prohibition on republishing an unchanged clone, and derived-publication rules;
- user journeys show granting, forking, and revocation as one scenario;
- license and provenance validation for derived publication fails closed when distribution rights are unknown.

## Reconsideration conditions

This decision will be reconsidered if a demonstrated need appears for exact-version grants or collaborative editing of one object. The latter requires its own ownership model and conflict resolution between people, not relaxation of this rule.
