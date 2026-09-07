---
description: "Separate immutable artifacts from mutable platform assets while keeping visibility in the authorization layer."
last_verified: "2026-09-07"
---

# ADR-0166: Separate artifact and asset storage by lifecycle

Accepted on 2026-09-07.

## Context

The platform currently configures one RustFS/S3 bucket for immutable artifact
bytes. Publication, private delivery, profile media, component media, and
platform-owned images have different ownership and lifecycle rules. Using one
bucket for public bytes and another for private bytes would make a visibility
change a storage migration and would couple authorization to object placement.

The MVP needs private publication and delivery to an owner or an active grant
recipient, owner-scoped component artifacts, owner-scoped presentation assets,
platform-owned assets, retry after network loss, and recoverable off-host
backups. It does not need general RBAC, per-user buckets, or direct client
credentials for RustFS/S3.

## Options

1. Keep one bucket and distinguish every class by key prefix. This minimizes
   configuration but gives artifacts, quarantined uploads, presentation assets,
   and platform files one policy and one operational lifecycle.
2. Use public, private, and platform buckets. This makes visibility physical,
   but changing visibility requires copying bytes and coordinating that copy
   with PostgreSQL.
3. Use one private artifact bucket and one private asset bucket. PostgreSQL
   remains the authority for public/private delivery; key prefixes identify
   ownership and purpose; backups use a separate off-host destination.

## Decision

Option 3 is accepted.

The **artifact bucket** stores immutable component and setup packages. The
server derives keys from the owner account and content digest. Equal bytes may
share one stored object only within the same owner namespace; owners never
share an object location.

The **asset bucket** stores append-only media bytes under closed namespaces for
users, components, and the platform. Replacing an avatar, component image, or
platform image creates a new object and atomically changes the PostgreSQL
pointer after validation; it does not overwrite bytes in place. Quarantined
assets are not deliverable.

Both buckets block public access and accept only server credentials. Public
means that the platform may deliver an authorized projection; it does not mean
that the bucket or object key is public. Public artifacts are available to any
reader. Private artifacts are available only to the owner or a recipient of an
active grant for the exact object and major line. Grants permit read, download,
install, and fork but not publication or mutation of the original.

Object keys are server-derived opaque locators and never authority. Account,
component, and platform prefixes are organization and defense in depth. Every
read starts from PostgreSQL metadata and authorization, then resolves the
stored location and verifies digest and size.

The existing plan-scoped API upload remains the only artifact writer. A retry
uses the same plan and exact digest, so a lost request or response can be
repeated without a second effect. Multipart upload and direct-to-storage client
upload are deferred until measured artifact size or retry cost exceeds the
bounded synchronous path.

PostgreSQL and both working buckets are backed up to a destination outside the
deployment host. A backup records the committed object inventory, and an
isolated restore verifies every referenced object's bucket, key, size, and
digest before the backup is accepted.

## Consequences

- storage configuration, readiness, and deployment create and verify two
  working buckets;
- object locations record the bucket role and owner binding in addition to the
  opaque key, digest, content ID, and size;
- existing global content-addressed locations migrate through additive columns,
  copy-and-verify, dual read, and cutover without deleting the old object during
  the compatibility window;
- publication visibility changes metadata only and never moves artifact bytes;
- media and artifact code share the S3 transport but retain separate validation
  and lifecycle rules;
- private delivery must have one server-side authorization predicate reused by
  API and CLI flows;
- bucket credentials, object keys, private asset originals, and backup contents
  remain absent from public projections, logs, passports, and audit payloads;
- real RustFS tests cover bucket isolation, owner isolation, idempotent retry,
  corruption, grant revocation, and restore verification.

## Revisit conditions

Revisit the two-bucket topology when a separate retention or encryption policy
cannot be expressed within the asset bucket, measured upload retries justify a
resumable multipart protocol, a CDN requires a dedicated public origin, or
availability requirements justify a multi-node RustFS deployment.
