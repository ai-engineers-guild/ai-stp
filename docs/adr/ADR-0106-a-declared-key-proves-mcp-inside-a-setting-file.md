---
description: "Decision to prove client MCPs inside a setting file by a declared key and read only server names."
last_verified: "2026-08-20"
---

# ADR-0106: A declared key proves client MCPs inside a setting

Status: accepted. Supplements `ADR-0054` regarding what discovery may open and
continues the line of `ADR-0055` and `ADR-0065`: the reader adapter declares
its boundary separately.

## Context

Discovery declared the `mcp` kind only for Claude Code. Its client servers live
in a separate `.mcp.json` file, and such a file proves itself by name: it exists
if and only if it was created for servers.

The other harnesses work differently. Codex and Grok Build keep servers in
`config.toml`, and OpenCode keeps them in `opencode.json` or `opencode.jsonc`—a
file already declared as the `setting` kind. The inventory therefore said
nothing about active servers on four of the five harnesses, although their
paths were known.

Simply declaring `mcp` on these paths is invalid. The existence of a setting
file proves nothing: it exists on any machine where the harness has run at
least once, and an empty `mcp` declaration is a normal way to run no servers.
That would produce a finding on every such machine, while the discovery
contract expressly forbids presenting something as evidence when it is not.

## Options

1. Declare a layout on the setting-file path without opening it. This is cheap
   and reads nothing, but creates a false finding wherever the harness is merely
   installed.
2. Read the entire setting file and place the server declarations in the
   finding. This answers the question but draws commands, URLs, and headers—
   which may contain tokens—into the output. That directly contradicts the ban
   on secrets entering passports, logs, and fixtures.
3. Read only server names beneath a declared key. This answers exactly the
   inventory question—which servers are declared, if any—and returns nothing
   beyond it.

## Decision

A layout may declare a key. A file with a declared key becomes an `mcp` finding
only when at least one server is declared beneath that key. Only server names
are read; they also become `evidence_refs` in the form key.name. Values beside
the name—command, arguments, URL, headers, and environment—are neither read nor
returned.

The key is declared by `codex` and `grok-build` (`mcp_servers` in
`config.toml`) and by `opencode` (`mcp` in `opencode.json` and
`opencode.jsonc`). Claude Code remains keyless: its `.mcp.json` proves itself by
name, and discovery does not open it.

Pi has no declared layout. Files named `mcp.json` do occur beneath its root,
but they are created by a user extension rather than the harness itself, and
observed instances disagree on the key. The Pi documentation table of contents
has no MCP page, so the verified gap `no_documented_mcp_client_config` is
declared instead of a layout.

## Consequences

- One file may produce two findings of different kinds: `setting` and `mcp`.
  The setting remains a setting and does not lose its meaning.
- Discovery opens the declared setting file, so the boundary is stated more
  precisely: values are not read, rather than all "contents of discovered
  files."
- An unreadable, oversized, malformed, or keyless file produces no findings.
  Guessing its contents would be exactly the heuristic forbidden by the
  discovery contract.
- JSONC parsing is implemented locally rather than through a dependency: only
  the key names of one hand-written file must be read, and a short parser in
  the discovery path is cheaper than a new package.
- Fixtures verify every declared key: an empty declaration, JSONC comments and
  trailing commas, malformed and oversized files, and a record whose value
  contains a token.

## Reconsideration conditions

Reconsider if a harness moves client servers into a separate file, if Pi
publishes documentation for its layout, or if a declared key starts appearing
in a nested form not covered by top-level reading.
