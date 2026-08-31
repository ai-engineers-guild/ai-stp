---
description: "Decision to work in the public tree and synchronize the private copy from it, retaining only unpublished content there."
last_verified: "2026-08-21"
---

# ADR-0110: Work lands in the public tree

Status: accepted. Changes the build direction from `ADR-0108` without
superseding its rules.

## Context

`ADR-0108` described the public tree as generated: the manifest names what is
published, `just public-build` assembles it, and `public_publish.py` sends it.
The direction is one-way—the private copy is the source.

`ADR-0109` made the public repository the deployment source. From that point,
the tree that deploys production and passes its own gate on standard GitHub
runners ceased to be a derivative artifact. The owner stated the task
directly: work occurs in the public repository, and the private copy is
synchronized from it.

The former direction cannot be retained under that rule. An edit made in the
public repository is silently reverted by the next `just public-build`: the
build does not know that it is overwriting another change. This already
happened with Dependabot pull requests—they had to be carried through the
private tree instead of merged where they were opened.

## Options

**Keep one direction and prohibit edits in public.** This is cheap but
contradicts the task and devalues the public tracker: a contributor who opens a
pull request is rejected for a reason invisible in the repository.

**Two independent trees with manual reconciliation.** This abandons the
manifest. Divergence becomes a matter of attention rather than verification.

**Reverse the direction while retaining the manifest as boundary owner.** The
public tree is the source of published content; the private copy is the source
of what the manifest withholds.

## Decision

Work takes place in `ai-engineers-guild/ai-stp`. The private copy is
synchronized from it through `just public-sync`.

Nothing new had to be declared for this, which is the main argument for this
form. The set of paths that synchronization does not overwrite is already
described twice: `[withheld]` in the manifest names unpublished content, and
`release_scripts/public_overlay/` names files the public tree carries
**instead of** those here. Everything else is published, so everything else is
imported.

Export and import are intentionally asymmetric. Export rejects uncertainty:
its error publishes private content, and fixing it requires rotating what
leaked. Import overwrites a local file, which Git makes reversible, so it
reports and writes loudly.

Deletion is part of the synchronization contract. Otherwise, a file deleted in
the public repository remains here forever, and the next export restores it—a
directional divergence detected only as a file nobody remembers adding.

Generated indexes are not imported as data. They enumerate documents in the
tree where they are built, and this tree has more documents, so
`just public-sync` invokes the generators afterward. If generators were not
invoked, `just docs-check` and `just back-static` detect the drift by comparing
generated output with its source.

Synchronization verification is circular: the published half of this copy
must match the public repository byte for byte except overlay files and
generated indexes, which are identified by a generator marker rather than a
list. `just public-sync-verify` answers this question.

## Consequences

The public tracker becomes real: a pull request is merged where it is opened.
The private copy ceases to be the source of code and remains the source of what
the public tree lacks—private-fleet workflows, internal reports, agent memory,
and decisions about infrastructure available only to it.

Leak protection is weakened, and this must be stated rather than silently
avoided. Previously, content scanning rejected a change **before** publication.
Now a change reaches the public repository before this copy sees it, so the
same report becomes a detector rather than a prohibition. Three things
compensate for this: secret scanning with push protection is enabled in the
public repository; the forbidden-name list remains in an unpublished file;
`just back-static` here still runs the report and breaks the gate on a finding.

`ADR-0108` continues to own **what** is published. Only the direction in which
bytes move changes.

## Reconsideration conditions

Reconsider if the private copy again becomes the source of published code, or
if a third tree appears that needs its own boundary.
