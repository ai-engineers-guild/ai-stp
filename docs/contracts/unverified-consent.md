---
description: "Session-scoped consent marker for unverified objects and durable exception records by publisher and major line."
last_verified: "2026-08-29"
---

# Consent to unverified objects

The requirements owner is `SPEC-006`; the decision is `ADR-0029`, and trust lanes are defined by `ADR-0016`. This document defines the machine boundary: consent forms, record fields, and events that invalidate consent.

The `search.include_unverified` key has been removed from CLI configuration: indefinite global consent to all unverified objects is supported neither in configuration nor in the profile.

## Forms of consent

| Form | Scope | Duration |
|---|---|---|
| request marker | current command or session | until the command or session ends |
| `publisher` record | all objects from a specific publisher | until revocation or an invalidating event |
| `object_major` record | major line `X` of a specific object | until revocation or an invalidating event |

The user explicitly selects the scope of a durable record; there is no “all unverified objects forever” form. Every form merely admits candidates into a separate `experimental` lane section of results: it does not move an object to `authoritative`, create platform verification, or waive mandatory installation checks.

## Consent record

A durable record stores:

- target: publisher identifier, or stable object identifier and major line number;
- scope: `publisher` or `object_major`;
- decision author and creation time;
- source: the command, session, or screen where consent was given;
- fingerprint of the candidate's permissions and capabilities at consent time: filesystem, network, and process permissions, credential requirements, and external connection points;
- list of objects from which the fingerprint was taken.

The last field distinguishes two facts that would otherwise look identical: a
fingerprint of objects that require nothing, and no observation at all. The
first is a real ceiling; the second covers nothing. A `publisher`-scoped record
takes the fingerprint as the union of what the target requires at consent time:
the user consents to what is shown, and anything beyond it is an invalidating
event.

A target with no objects in the registry cannot be approved: a “candidate
fingerprint” has no meaning without a candidate, while stored emptiness would
later be read as consent and behave like a denial.

Records belong to the user, are stored in the local registry, and synchronize as ordinary revisioned entities. A record contains no secrets or environment values.

## Invalidating events

A record stops covering a version if, compared with the stored fingerprint, that version requires new permissions, processes, network access, credentials, external connection points, managed paths, or native surfaces. A new major line is not covered by the previous line's `object_major` record.

An invalidating event does not silently delete the record: the user is shown the exact reason, and continuing requires a new explicit decision. User revocation takes effect immediately for future requests.

## Usage

Results label every `experimental` candidate with the consent source: the request marker or a specific record. The recommendation trace and installation plan record the consent source and permission fingerprint under which consent was considered valid.

Both search and selection read the records. Both scopes are consulted from
narrowest to broadest: the object's `object_major` record takes precedence over
its publisher's `publisher` record, otherwise a more specific record could not
override the broader one. The request marker belongs to `select eligibility`;
`select propose` does not have it because a proposal is a step toward
installation and may rely only on a durable decision.
