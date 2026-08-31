---
description: "Decision to retain GitHub archived state as external evidence rather than an automatic lifecycle transition."
last_verified: "2026-08-13"
---

# ADR-0082: GitHub archived state remains external evidence

Status: accepted.

## Context

A public GitHub repository may be archived, renamed, transferred, or reopened.
This is a useful obsolescence signal, but not an author or moderator decision
about the lifecycle of a published version. Automatic `blocked` status or
target deletion would mix an external fact with policy and make a network
failure grounds for an irreversible action.

## Decision

The CLI reads the official `GET /repos/{owner}/{repo}` only for the source of
the exact local version and stores an append-only observation. The stable
identity is the GitHub repository id; `full_name` is a mutable coordinate.
Archived state creates a dated `deprecated` proposal, but does not change the
lifecycle. An offline response uses the latest successful observation with a
TTL. Errors and lack of access remain `unavailable`.

The transport uses a conditional request, does not follow redirects, and has no
credential surface. Therefore, the first version receives public metadata only,
while a private repository remains indistinguishably `unavailable`.

## Consequences

History preserves archive and subsequent unarchive events. Rename/transfer does
not lose identity. Rate limits and outages do not create false obsolescence.
Platform/web may later project the same shared contract, but the local
implementation does not claim account-wide completeness.

## Reconsideration conditions

The decision is reconsidered when adding another forge, an automatic lifecycle
workflow, account-wide polling, or a server-owned cache. Each changes authority
or the network boundary and requires a separate contract.
