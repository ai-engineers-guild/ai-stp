---
description: "Fail-closed provenance of installed GitHub components from a bounded chain of manifest evidence."
last_verified: "2026-08-09"
---

# ADR-0055: Exact Provenance of Installed Components

Status: accepted. Continued by `ADR-0106` for MCP discovery inside setting files.

## Context

A path in the cache does not prove a component's source. A directory name can be spoofed,
a Git remote may contain credentials, and running Git or the harness during
read-only discovery expands the executable and side-effect surface. At the same time,
issue `#231` requires discovering global components from GitHub with stable
identity and provenance.

Claude Code stores installed plugins in a versioned cache, distinguishes the
marketplace source from the plugin source, and copies installed bytes into
`~/.claude/plugins/cache`. A relative plugin source belongs to the marketplace
repository, while separate `github`, `url`, and `git-subdir` sources may have
their own exact SHA.

## Decision

The CLI uses a separate bounded source adapter. For Claude Code, it binds:

1. the supported version 2 `installed_plugins.json` ledger;
2. `known_marketplaces.json` with the GitHub `owner/repo`;
3. the manifest at the computed path
   `plugins/marketplaces/<name>/.claude-plugin/marketplace.json`;
4. a plugin entry with an allowlisted source kind;
5. an existing install path strictly within
   `plugins/cache/<marketplace>/<plugin>`;
6. a full 40-character commit SHA.

The `installLocation` field is not used. The adapter does not run Git or the harness,
does not access the network, does not accept URLs with userinfo, and does not echo
manifest contents or system error text. Each manifest is limited to four MiB. A
floating ref without an observed exact commit does not become exact provenance.

A GitHub finding receives `provenance.kind=github`, `state=exact`, a canonical
HTTPS repository, revision, optional subpath, package name/version, and a closed
list of evidence kinds. A regular layout finding receives only
`filesystem/local`. An installed plugin without a proven GitHub source remains
visible as `package/observed` with package name/version, but without repository
or revision. Inconsistent combinations are rejected by the machine schema.

A malformed, unknown-version, or incomplete manifest is not guessed. The command
returns a safe diagnostic code and continues independent layout discovery.
Project/local scope from the global installation ledger is not elevated to global.

Upon explicit acceptance, the exact `repository`, `revision`, `subpath`, and package
identity are stored in the passport together with `content_digest`. `candidate_id`
includes provenance; a change in source evidence creates a different candidate
but does not change the already created logical Component.

## Consequences

- a global GitHub plugin can be safely addressed and accepted without guessing
  from the directory name;
- service buckets `plugins/cache`, `data`, and `marketplaces` are no longer emitted
  as separate plugins;
- an unknown new ledger requires an explicit update to the adapter and fixtures;
- exact npm/archive/Pi package provenance requires separate adapters;
  an observed installation remains visible but is not presented as GitHub;
- provenance proves the asserted installation chain but is not a platform
  attestation of code quality or security.

## Reconsideration Conditions

The decision is reconsidered upon the availability of a documented versioned
installed plugins API, a change to the cache layout, or the emergence of a signed
installation manifest that allows the internal ledger to be replaced with
stronger evidence.
