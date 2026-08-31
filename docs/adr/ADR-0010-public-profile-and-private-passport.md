---
description: "Decision to separate the public profile from the passport."
last_verified: "2026-08-03"
---

# ADR-0010: Separate the public profile from the passport

Accepted on 2026-08-03. Superseded by `ADR-0023-public-profile-as-authored-object.md`: the separation remains, but the public profile ceased to be a projection of selected passport fields and became a separately authored object. Read this record only for the context of the original choice.

## Context

A developer passport contains the environment, installed tools, habits, and choice history — data the user has no reason to publish. At the same time, the catalog needs author identity for published objects. Publishing an object and making an author public are different decisions and must not be linked implicitly.

## Decision

The Developer Passport remains a private canonical object. Public visibility is implemented as a separate projection containing only fields explicitly selected by the user.

## Consequences

The schema has two separate objects rather than a public-visibility flag inside the passport. The projection is populated only with explicitly selected fields. Synchronization, component publication, and granting access to another account do not change passport visibility. A negative test for leakage of private fields into the public projection is required.
