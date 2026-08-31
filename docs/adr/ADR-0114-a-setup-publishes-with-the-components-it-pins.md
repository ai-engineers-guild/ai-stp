---
description: "Decision to publish a setup and the components it pins as one set of plans with one confirmable digest."
last_verified: "2026-08-21"
---

# ADR-0114: A setup is published with the components it pins

Status: accepted.

## Context

A setup cannot become public before its exact pins: `setup_pin_aggregate`
rejects a setup whose pinned component has not passed its scan, correctly so—a
public setup would otherwise reference something absent from the catalog.

This implied an undeclared sequence of actions. The setup owner had to publish
each component through a separate plan with separate confirmation, wait for
each one, and only then proceed to the setup. For an imported configuration of
twenty-nine components, that meant thirty plans and thirty confirmations.

Worse, the final step was unavailable: `publication plan` in the CLI hard-coded
`object_kind="component"`, and `REQ-3801` described it as a component command.
A setup could not be published from the CLI at all. Corpus publication was
performed by the internal `first_party_launch_publication.py` tool, which knew
and privately retained the required order.

Locally, the same operation has long been a single action. `setup import
register` materializes component artifacts, component passports, and the setup
graph "together or not at all"—`register_graph` states this directly. The gap
was not in the domain model but in the publication boundary's ignorance of it.

## Options

**Leave it as is and document the order.** Inexpensive, but assigns to a human
what the machine knows exactly: which pins are unpublished and in what order to
confirm them. A documented manual sequence is an error that has not happened
yet.

**One server plan for the whole graph.** Closest to "components are registered
as part of the setup." But one plan for N objects breaks everything built on a
plan as the unit: `plan_hash` over one object, scanning by `content_digest`, the
catalog row, idempotency, and resumption after an indeterminate result. A server
contract change of this size is not justified for client convenience.

**A set of plans and one confirmation over it.** Plans remain what they were—
one per object. The only new behavior is that the client creates them all in
one call, orders components before the setup, and confirms the set with one
digest.

## Decision

Setup publication is performed by `setup publish plan` and `setup publish
confirm` and is **one decision over the entire graph**.

`plan` creates one plan for each pinned component that is not yet public and
one for the setup itself; an already-public participant is listed and not
planned again. The set is stored locally just as `report_plans` stores the exact
preview for subsequent confirmation: `plan_id` cannot be reconstructed by
calculation; it exists only because the plan was created.

`set_digest` covers the ordered participant list—the role, kind, `stable_id`,
version, `plan_hash`, and "already published" flag. Any difference produces a
different digest and therefore a different decision.

`confirm` confirms participants in set order: components, then the setup. If a
participant fails, confirmation stops and the set enters `partial`—a resumable
state, not a failure: published objects remain published.

## Consequences

The guarantee for which confirmation exists remains undiminished: publication
still requires explicit confirmation of the exact hash. What changes is that
the hash covers the whole graph rather than one node.

`publication plan` remains a component command and does not change. Publishing
one component remains the direct path; a set is needed where an object has pins.

The "components before setup" order ceases to be knowledge held by an internal
tool and becomes a command property. `first_party_launch_publication.py`
retains its own batch mode: it publishes the entire corpus rather than one
graph, which is a different task.

Set state lives locally. A second plan for the same setup version replaces the
open set rather than sitting alongside it: two open sets for one version differ
only in which is stale, and nothing on the wire communicates that.

Requirements: `SPEC-038` `REQ-3810`–`REQ-3812`. Machine surface:
`docs/contracts/cli-publication.md`.
