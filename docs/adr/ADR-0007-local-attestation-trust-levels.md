---
description: "Decision not to treat a device signature as platform execution."
last_verified: "2026-08-03"
---

# ADR-0007: Do not treat a device signature as independent platform execution

Accepted on 2026-08-03.

## Context

An author controls their own device and can modify the local tool or its environment before a report is produced. A cryptographic signature protects the report's provenance and integrity but does not prove honest execution.

## Decision

A device-signed local report is stored as author confirmation. The server separately verifies device/account status, the signature, digest, schema, and non-executable structural rules. Installation and runtime checks are separate evidence levels.

## Consequences

Cards and the API do not combine different evidence sources into a single `verified` field. An automatic recommendation requires an explicitly defined minimum set of levels.
