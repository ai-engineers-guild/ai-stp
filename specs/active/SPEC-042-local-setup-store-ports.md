---
description: "SPEC-042: Local versioned ports for controlled SX and APM import."
last_verified: "2026-08-13"
---

# SPEC-042: Local setup-store ports

## Purpose

The agent can discover and inspect the local state of a compatible setup store, see the exact conversion, and register available components only after confirmation. The external store remains the source of the snapshot but does not gain ownership of the registry or the final harness state.

## Scope

The port reads only `sx.toml` schema 2 or `apm.lock.yaml` version 1/2 within an explicitly named root. It does not run SX/APM, does not use the network, and operates without the vendor CLI. Import writes only private local drafts; writing back to the external store or harness target is not supported and would require a separate provider plan.

## Terms

- **Store descriptor** — the version of the common port, adapter, and exact snapshot manifest.
- **Mapping** — an explicit decision about the canonical representation or the reason for omission of one external entry.
- **Import key** — a content-addressed association of the adapter, snapshot, and external identity with an already created local object.

## Requirements

- `REQ-4201`: Vendor-neutral `setup-store-port/1` separates discovery, inspect, content-addressed plan, and confirmed import; the vendor schema does not leak into the command contract.
- `REQ-4202`: Discovery and inspect do not open the local registry for writing, do not execute the vendor CLI, and constrain the manifest by size, entry count, key uniqueness, and safe root.
- `REQ-4203`: The SX adapter accepts schema 2 and explicitly maps `skill`, `rule`, `agent`, `command`, `mcp`, `hook`, `claude-code-plugin`, and `app-plugin` to canonical component kinds. Only an existing `source-path` is imported; an HTTP/Git source remains an omission in offline preview.
- `REQ-4204`: The APM adapter accepts lock version 1/2 and derives component boundaries only from safe `deployed_files` in known native layouts. Exact version, source coordinate, and available digest are preserved as observed provenance.
- `REQ-4205`: An unknown type, field, collection, unsafe path, or unavailable source is not guessed. Unknown fields are included in a bounded report, and an unrepresentable entry receives an explicit omission reason.
- `REQ-4206`: The plan shows mappings, omissions, collisions, and trust implications. The digest binds the entire inspect report, the content digest of every available local path, and the absence of external/target writes to the exact manifest bytes.
- `REQ-4207`: Import rebuilds the plan, requires the exact digest and `--confirm`, atomically accepts the actual local bytes through component adoption, and persists the idempotency key. Repeating the same snapshot returns the previous identifiers without creating a new revision.
- `REQ-4208`: Imported passports remain private, local/imported, and do not receive `author_verified` or `component_verified`. Subsequent publication follows the standard enrichment and validation process without exceptions for vendor metadata.

## States and errors

A mapping has the state `component` or `omitted`. Import returns `imported` or `already_imported`. A collection or remote-only source remains an omission rather than a partial object. An incompatible version, ambiguous manifest, collision, stale digest, or unsafe or missing path produces a typed refusal before any new object is written.

## Security and privacy

Reading is limited to a regular, non-linked manifest and declared local paths within the root. Environment values and credentials are not read separately and are not included in the conversion report. Import uses the existing component-adoption constraints for secrets, size, and a safe deterministic artifact. All new passports are private.

## Compatibility and migration

The exact contracts read are pinned to the public SX and APM sources in `docs/contracts/setup-store-ports.md`. A newer incompatible version is rejected with `AI_STP_SCHEMA_UNSUPPORTED`; adding a version requires a fixture, mapping review, and an update to this SPEC. The presence of the executable is diagnostic information, not a precondition for an offline snapshot.

## Acceptance criteria

| Requirement | Executable evidence |
|---|---|
| `REQ-4201` | Strict common schemas and machine help describe four separate commands. |
| `REQ-4202` | A test compares the manifest and registry state before and after discovery and inspect; duplicate keys and bounds violations are rejected. |
| `REQ-4203` | The SX fixture contains an importable path, an unknown type, and a collection with explicit omissions. |
| `REQ-4204` | The APM fixture reduces a skill directory and prompt file to two exact canonical boundaries. |
| `REQ-4205` | Unknown top-level and dependency fields are visible in the report; an unknown type is not imported. |
| `REQ-4206` | Changing the manifest or local component bytes changes the digest, and stale apply is refused before any write. |
| `REQ-4207` | Applying the same plan twice creates one Component and returns `already_imported`. |
| `REQ-4208` | Passport validation does not consider an imported draft ready or platform-verified. |
