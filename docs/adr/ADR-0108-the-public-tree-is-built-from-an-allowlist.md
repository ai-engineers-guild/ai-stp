---
description: "Decision to build the public repository from an allowlist manifest with forbidden-content checks rather than deleting excess content from a copy."
last_verified: "2026-08-20"
---

# ADR-0108: The public tree is built from an allowlist

Status: accepted. Clarifies `#188`, which planned to make this repository itself
public: what becomes public is a tree assembled from it, not this repository.
The build direction was changed by `ADR-0110`: work takes place in the public
tree, and the private copy follows it.

## Context

This working repository contains more than the implementation: agent memory
with host names and private task numbers, review screenshots and development
logs, dated internal plans, decisions about the private runner fleet, and a
runbook for a specific deployment. It cannot be published in full, while the
implementation must be published.

The costs of errors are asymmetric. An omitted file is fixed by naming it; a
leaked file is fixed by changing what leaked.

## Options

1. Make the repository public as-is after removing excess content. A one-time
   cleanup does not survive the next commit: a new internal file silently
   becomes public.
2. Maintain a public copy beside it and edit both. The copy diverges from the
   original, violating the rule that each fact has one owner.
3. Build the public tree from a manifest that enumerates what is published.

## Decision

Option 3 is accepted. `release_scripts/public_manifest.toml` enumerates roots
that are published and paths that are withheld, each with a reason. A path that
nobody names remains private: the build fails if a root appears in the internal
tree about which the manifest says nothing.

This is the reverse of the native-component discovery rule, which uses a
denylist. There, an error hides a finding; here, it publishes one. The default
direction is chosen according to the cost of an error.

The second boundary is content scanning. Suitability is decided by directory,
while leakage happens by string, so a published directory does not promise
that every string in it is public. The build fails if a published file contains
the name of a private fleet class, a private repository, or a deployment-host
identity. The overlay is scanned under the same rules: a file written for the
public tree can name a private host just as easily.

The forbidden list judges what is disclosed, not what sounds internal.
`/home/ubuntu` was included and then removed: it is Ubuntu's ordinary default
user path, the adjacent SSH configuration points to `ssh.github.com`, not our
server, and it names a key path rather than a key. A reference deployment is
exactly what the open repository should provide.

Withheld content is not edited; where referenced, it is replaced by a stub. An
abridged operations document reads like a complete document missing precisely
the details for which it is consulted; a stub states the reason and does not go
stale.

## Consequences

- The public tree is generated rather than maintained: edit the source, then
  run `just public-build`. `just back-static` invokes the report, so an unnamed
  root or leak breaks the gate rather than being discovered during publication.
- The assembled tree is its own repository without inherited history. This is
  also a correctness condition: tools inside the tree ask Git which documents
  exist and receive an empty answer in a directory owned by, and ignored by,
  the parent repository.
- Generated indexes are rebuilt against the assembled tree: an index copied
  unchanged would reference withheld records.
- The assembled tree lives inside the source and is a complete copy of it, so
  repository traversal must skip it; otherwise the check for a unique table
  finds its own copy and reports a duplicate. The output directory is named
  alongside `.venv` and `node_modules`.
- Tests asserting the contract of private workflows are not published.
  Published unchanged, they would be false rather than redundant: the public
  tree runs on GitHub runners.

## Reconsideration conditions

Reconsider if this repository itself becomes public and the build loses its
purpose, if currently withheld content becomes publishable, or if a second
consumer needs a tree composition different from `ai-stp`.
