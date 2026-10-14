---
description: "Decision to coordinate multiple scope-specific provider operations as one recoverable consumer transaction."
last_verified: "2026-10-14"
---

# ADR-0145: Multi-root installation is a consumer-owned recoverable transaction

Status: accepted.

## Context

A setup may have adaptations for global, user_root, and project, while provider
protocol v3 deliberately plans and applies one target and one projection profile
at a time. A single setup installation therefore may require several independent
filesystem roots.

No portable filesystem primitive atomically renames an arbitrary set of
configuration roots, which may be on different filesystems. Provider-owned
preparation can establish unchanged preconditions at every root but cannot
remove the interval between subsequent publications.

The owner excludes automatic configuration backups. Current components support
explicit forward recovery and, from 0.0.94, durable preparation and exact
cancellation before publication. These are optional capabilities of provider v3;
older releases cannot execute the native aggregate boundary.

## Decision

ai-stp owns a recoverable multi-root operation above the provider's single-root
configuration lifecycle. Providers remain the only writers of final native state.

The consumer resolves the complete setup graph and every scope first, orders
roots as global, user_root, project, and obtains an exact non-mutating plan for
each. One aggregate digest binds every original child plan, physical root,
provider release, package and desired effect. An optional registered project and
exact selection are bound separately from the configuration roots.

One SQLite transaction admits the parent and every child reservation. Only
desired package bytes are retained. Every component must prepare unchanged
configuration before the parent durably enters publication. Children then apply
in order, with independent file/mode/ownership readback and durable checkpoints.
The parent becomes verified only after every child has a verified receipt and
all roots pass a final readback. Complete project attribution commits with that
parent receipt; a later selection or project revision is not overwritten.

Cancellation is available before publication begins. Once publication may have
started, recovery resumes the original durable component operation and advances
forward. It never restores an older database over later filesystem changes,
extends an unadmitted plan's expiry, or silently discards partial completion.
There is no promise of instantaneous cross-root visibility. An unfinished parent
remains applying and exposes preparation and completion for each child.

A parent owns its exact child operation IDs and reserves all physical roots,
including already completed children, until it settles. Public child mutations
cannot bypass it. A lost reply after child completion is reconciled from that
child's terminal receipt. Settled replay reads history without touching targets,
package sources or the network. Older native writers are fenced by the
configuration namespace marker after their held target locks drain.

## Consequences

- The operation needs component preparation support; the mandatory single-root
  provider core and existing single-root plans remain usable.
- Failures leave explicit durable progress and a forward recovery path, without
  creating configuration backups or claiming compensation that did not occur.
- A partial scope receipt cannot identify a complete installed setup.
- A setup needing one root keeps the existing single-root path.
- Reservations coordinate writers sharing one state parent. Independent state
  parents still rely on the provider's own target journal and preconditions.

## Reconsideration conditions

Reconsider if every supported platform provides one proven primitive for an
atomic exchange of all selected roots, or if a future provider operation owns
all roots itself and can prove that stronger postcondition.
