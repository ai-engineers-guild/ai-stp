---
description: "Closed list of anonymous telemetry ping fields, sending conditions, and excluded data."
last_verified: "2026-08-21"
---

# CLI telemetry ping

The requirements owner is `SPEC-013` (`REQ-1316`–`REQ-1319`); the decision is
`ADR-0112`. This document defines the machine boundary: the list of fields,
their sources, and sending rules.

All client telemetry egress consists of one unauthenticated HTTPS `GET`. It has
no body, cookie, catalog token, or GitHub authorization. The field list is
closed: a field outside the table requires changing this document, `SPEC-013`,
and `ADR-0112`, rather than merely extending the request.

## Request fields

| Field | Example | Source |
| --- | --- | --- |
| `os` | `windows`, `linux`, `darwin` | device platform |
| `harness` | `codex` | harness where the component was installed |
| `harness_version` | `0.140.1` | harness version as reported by the toolchain |
| `ai_stp_version` | `0.1.0` | CLI version |
| `component_type` | `mcp` | component kind from the eight declared kinds |
| `name` | `serena` | public component name |
| `source` | `platform`, `github` | where the object is publicly identified |
| `id` | platform stable id **or** `https://github.com/org/repo` | component passport |
| `version` | `1.2` | exact component version |
| `anon` | random local UUID | local data directory |

`source` is `platform` when the object is registered on the platform. Otherwise,
it is the public GitHub source from the passport. If there is nothing to identify
publicly—no name or kind—the request is not sent at all.

## Data never included

Local paths, private repositories, account identifiers, device keys, email,
project names, target paths, environment-variable names and values, file
contents, and MCP server headers and arguments.

`anon` distinguishes one CLI installation from another and nothing more. It is
not equal to `device_id`, is not associated with an account, resides in the
local data directory rather than configuration, and is not combined with public
catalog usage counters
(`REQ-1315`).

## When it is sent

After a `verified` application with the `install` or `update` action—one request
per component actually installed. A setup with three components produces three
requests.

It is not sent for `backup`, `rollback`, `remove`, or any reads; it is not sent
in offline mode or in tests.

## Failures

A network error, timeout, or any non-2xx response is silently ignored. The
installation remains `verified`: its result is a property of the target, not of
the collector. No batch retry is performed.

## Configuration

The fields belong to `cli-config.md`: `telemetry.enabled`, which defaults to
`false`, and `telemetry.url`. Setting `telemetry.enabled=true` without using the
consent command is rejected—consent is an event, not a value.
