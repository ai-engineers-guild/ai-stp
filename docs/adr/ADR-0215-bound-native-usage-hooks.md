---
description: "Bind native usage observations to a verified local installation without exposing corporate credentials to components."
last_verified: "2026-09-26"
---

# ADR-0215: Bound native usage hooks

Status: accepted; implementation and live harness validation are in progress.

## Context

The runtime usage outbox accepts closed event records, but a callable recording
function alone does not observe harness execution. Components cannot choose a
corporate destination or receive credentials. A tool's pre-execution notification
does not prove it passed permission checks or began execution.

## Decision

Native hook adapters resolve exact component coordinates and corporate context
from the current verified provider installation and its immutable local binding.
They refuse superseded, removed, ambiguous, or drifted installations. A native
tool identifier must match the installed component's declared native identity.
Only supported execution evidence creates an invocation; permission checks and
unsupported lifecycle events do not. Session and tool-call correlation is hashed
into one event ID for retry and fallback reconciliation.

Hook payloads are processed in memory. Only the existing closed event fields
reach the local outbox. The adapter does not send network requests or modify
harness files. Hook configuration is ordinary provider-managed component
content, included in the reviewed installation plan. It contains no credentials
or remote callbacks. Existing native trust checks remain in force.

## Consequences

Coverage is explicit per harness and component kind. A supported adapter is not
proof that a hook has been installed, trusted, or executed. Unsupported kinds
remain unsupported or agent-reported; instruction and setting loads never
become component invocations. Live evidence must show execution, local queuing,
delivery, and report attribution separately.
