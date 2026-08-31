---
description: "Bounded discovery of MCP server packages only through an agreed chain of package manifest and entry point."
last_verified: "2026-08-10"
---

# ADR-0065: Manifest-led discovery of MCP server packages

Status: accepted.

## Context

The MCP client configuration file and the server implementation have the same product type
`mcp`, but different native roles. An exact `.mcp.json` was already discovered as a client
config, while server source packages were invisible. Searching for the substring
`mcp`, `server.py`, `hooks`, or Dockerfile would produce many application, test, and docs
false positives and would require arbitrary reading of the project.

## Decision

Within an explicitly selected project root, the CLI performs bounded manifest-led traversal. It
does not follow symbolic links, excludes dependency, cache, build, documentation, fixture,
and test trees, and limits depth, the number of directories, the number of entries, and the
size of each metadata or source file read.

A Python candidate requires all of the following: `pyproject.toml`, an `mcp` or
`fastmcp` dependency, a declared `project.scripts` entry point, existing exact module
source, and an MCP SDK import in that source. A TypeScript candidate requires
`package.json`, an official SDK dependency, a declared `bin` or script source,
and an SDK import in the exact entry file. Nothing is executed.

The candidate receives `component_type=mcp`, `native_role=mcp_server`, its own
source root, entry points, proven `stdio`/`http` transport capabilities, and
relative evidence refs. An exact `.mcp.json` receives
`native_role=mcp_client_config`. A launcher manifest becomes additional
evidence only when bounded content references an already proven entry point;
the launcher itself does not create a candidate.

## Consequences

- nested Python and TypeScript packages in a monorepo become explainable;
- docs, tests, frontend hooks, Dockerfile, and a name containing `mcp` are not by
  themselves evidence of a server;
- an unknown transport remains an empty list rather than being guessed;
- acceptance of a source package preserves the role, entry point, transports, and evidence
  refs in a content-addressed local revision;
- a new ecosystem or manifest format requires a separate fixture and an update to
  this adapter.

## Reconsideration Conditions

The decision will be reconsidered if a universal signed MCP package
manifest or an official cross-language discovery protocol emerges.
