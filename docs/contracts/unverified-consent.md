---
description: "Session-scoped consent marker for unverified objects and durable records by publisher, major line, and authorized task profile."
last_verified: "2026-09-05"
---

# Consent to unverified objects

The requirements owner is `SPEC-006`; the decisions are `ADR-0029` and
`ADR-0159`, trust lanes are defined by `ADR-0016`, and full-task authority is
`ADR-0150`. This document defines the machine boundary: consent forms, record
fields, precedence, and events that invalidate consent.

The `search.include_unverified` key has been removed from CLI configuration:
indefinite global consent to all unverified objects is supported neither in
configuration nor in the profile. Scope `task` is not that key: it names one
authorized full-auto profile, is revocable, and loses to a narrower exclusion.

## Forms of consent

| Form | Scope | Duration |
|---|---|---|
| request marker | current command or session | until the command or session ends |
| `publisher` record | all objects from a specific publisher | until revocation or an invalidating event |
| `object_major` record | major line `X` of a specific object | until revocation or an invalidating event |
| `task` record | authorized full-auto profile | until revocation |

The user explicitly selects the scope of a durable record. `task` accepts only
the target `full-auto`. Every form merely admits candidates into a separate
`experimental` lane section of results: it does not move an object to
`authoritative`, create platform verification, or waive mandatory installation
checks.

## Consent record

A durable record stores:

- target: publisher identifier, stable object identifier and major line number,
  or the authorized profile name `full-auto`;
- scope: `publisher`, `object_major`, or `task`;
- decision author and creation time;
- source: the command, session, or screen where consent was given;
- fingerprint of the candidate's permissions and capabilities at consent time:
  filesystem, network, and process permissions, credential requirements, and
  external connection points;
- list of objects from which the fingerprint was taken.

The last field distinguishes two facts that would otherwise look identical: a
fingerprint of objects that require nothing, and no observation at all. The
first is a real ceiling; the second covers nothing. A `publisher`-scoped record
takes the fingerprint as the union of what the target requires at consent time:
the user consents to what is shown, and anything beyond it is an invalidating
event.

A `task` record is not a fingerprint of objects. Empty `observed` is expected:
the authority is the named profile, not a candidate shape. Capability growth
and a new major line do not invalidate it.

A `publisher` or `object_major` target with no objects in the registry cannot
be approved: a “candidate fingerprint” has no meaning without a candidate,
while stored emptiness would later be read as consent and behave like a denial.

Records belong to the user, are stored in the local registry, and synchronize
as ordinary revisioned entities. A record contains no secrets or environment
values.

## Invalidating events

A `publisher` or `object_major` record stops covering a version if, compared
with the stored fingerprint, that version requires new permissions, processes,
network access, credentials, external connection points, managed paths, or
native surfaces. A new major line is not covered by the previous line's
`object_major` record.

An invalidating event does not silently delete the record: the user is shown
the exact reason. Under an active `task` grant the fingerprint miss is not a
stop: task authority covers, and the object remains `experimental`. Continuing
without task authority requires a new explicit publisher or object-major
decision. User revocation takes effect immediately for future requests.

## Precedence

Search, selection, and installation read the records per candidate. Scopes are
consulted from narrowest to broadest:

1. A revoked `object_major` or `publisher` record is an exclusion. It answers
   before a broader grant, including `task`.
2. An active `object_major` record that still matches the fingerprint answers
   before `publisher`.
3. An active `publisher` record that still matches the fingerprint answers
   before `task`.
4. An active `task` record covers without a fingerprint or major ceiling.
5. Otherwise a fingerprint miss reports that miss; otherwise there is no
   durable consent.

The request marker belongs to `select eligibility`; `select propose` does not
have it because a proposal is a step toward installation and may rely only on
a durable decision.

## Usage

Results label every `experimental` candidate with the consent source: the
request marker or a specific record as `scope:target`. The recommendation
trace and installation plan record the consent source and, for fingerprint
records, the permission fingerprint under which consent was considered valid.
