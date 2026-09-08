---
description: "Sync carries immutable version snapshots and journals incomplete legacy references without blocking unrelated history."
last_verified: "2026-09-08"
---

# ADR-0173: Self-contained version synchronization

Status: accepted

## Context

Version release stores a snapshot independently of the editable draft head.
The existing sync sender walks draft ancestry and attaches only version
coordinates. A fresh receiver cannot materialize a released version whose
snapshot was never in that ancestry. Releasing after an accepted push also
leaves the draft revision unchanged, so the old replay key suppresses the update.
A legacy incomplete version reference currently rolls back every later page.

## Decision

Component/setup sync carries the exact released passport snapshot beside its
version metadata. The current draft head remains independent. Both its content
and the version closure participate in outgoing replay identity; an outstanding
request is completed with its original event/key before a newer payload is sent.
A version-only update is a child of the prior accepted transport revision for
that same local head, never an invented parent for an unrelated remote edit.

Receivers verify snapshot identity, kind and digest before storing it without
moving the draft head. Existing immutable version collisions remain explicit.
Payload and account checks apply recursively; artifact and backup bytes remain
outside synchronization. The version list stays bounded.

A valid legacy event with an unavailable version snapshot retains the exact
reference in an account-scoped local pending journal. The event and cursor are
committed together with that journal. Pull reports partial until all pending
references have matching snapshots; a later valid event can supply them. This
is not event abandonment: the original event remains retained and no version is
invented, replaced or declared available. Invalid hashes, foreign coordinates,
forbidden payloads and version collisions still roll back the page.

## Compatibility and consequences

The outer event/receipt protocol remains v1; snapshot is an optional extension
of the existing version metadata. New readers retain old valid streams. Old
readers that cannot materialize a snapshot still need an update; they do not
silently rewrite it. Local schema migration adds the pending journal. CLI pull
adds explicit progress and pending-reference fields; canonical shapes belong to
sync-event.md and requirements to SPEC-009. No server-side merge or installation
of a target is introduced.
