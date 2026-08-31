---
description: "Machine contract for the local context budget, capability delta, and blast radius."
last_verified: "2026-08-15"
---

# Selection impact

## Commands and boundary

`select impact` reads an exact candidate setup and an optional exact baseline
from the local registry. `select blast-radius` reads reverse references to an
exact component. Both commands have mutability `read`, return
`freshness=local_snapshot`, do not use the network, and do not change selection,
lifecycle, operation, or target.

Command parameters belong to the generated `help --agent`, and response fields
belong to the `cli-selection-impact-report` and `cli-blast-radius-report`
schemas; they are not duplicated here.

The baseline may be named by an exact identifier and version pair. If a project
is named instead, the CLI first uses the last verified installed setup for that
project and harness, and, if none exists, the currently selected setup. The
`baseline_source` field distinguishes these cases; the absence of both sources
leaves the delta unavailable instead of inventing a zero baseline.

## Context measurement

The estimator is a separate versioned contract. An exact byte profile is useful
as a reproducible upper bound for its own unit, but does not claim to match a
model tokenizer. The codepoints/4 profile is always called an estimate. Both
operate locally and do not transmit private content externally.

Always-loaded and conditionally-loaded content are separated in the report. A
signed delta is returned for the baseline: a negative number means a reduction.
Binary/non-UTF-8 content has status `unavailable`; a missing measurement is not
replaced with a zero estimate.

## Cost and capabilities

The price profile is supplied as a separate JSON file and is bound to the
estimator profile. It contains the price of one million input tokens, currency
USD, model, HTTPS source, `fetched_at`, and `expires_at`. Without the file, cost
is unavailable; after `expires_at`, it is stale and amount is absent. The price
profile is not an eligibility input.

The capability snapshot and delta preserve the specific added and removed
native IDs, endpoints, component coordinates with credential requirements, and
permissions. There is no single score: distinct consequences cannot be hidden
behind one number.

## Blast radius

The reverse index is computed from verified local setup passports, the active
selection, and the verified operation log. It does not claim account-wide or
organization-wide completeness: `authority_boundary=local_registry` limits the
meaning of the response to the current registry file and its device. All
lifecycle scenarios only name affected references; `action=none` excludes any
automatic update/uninstall.

## Server account projection

The local v1 contract does not change. `GET /v1/selection/blast-radius` has been
removed: blast radius remains CLI-only (`SPEC-049`). Web displays the absolute
context budget of the visible exact setup in the card's right rail after Author
and before CLI installation and Version history: a collapsed summary and a
nested `select impact` command separate from the CLI installation block. Web
does not display account blast radius or an installed baseline guessed by the
server.
