---
type: article
slug: compatibility-gates
locale: en
title: Compatibility is a gate, not a suggestion
description: "Exact pins, the setup graph, harness support and policy either produce a plan or a refusal. The refusal is the product."
published_at: 2026-08-12
tags: [compatibility, setup, policy]
draft: false
---

A useful setup is more than a list of attractive components. Every pinned version must fit the target harness, the native surface, and the trust policy before a provider is allowed to apply it. Compatibility in ai_stp is a gate: the compiler either emits a deterministic plan or names the edge that failed. It does not “mostly work” and it does not silently upgrade a pin so that the graph becomes pretty.

Agent reasoning does not sit in front of that gate. Mechanical constraints run first. An ineligible candidate never enters the selection input, so it cannot be smuggled back as free text.

![Compatibility signals converging on one deterministic decision](/content/illustrations/compatibility-gate.svg)

## Start with exact inputs

The builder receives exact component versions and a concrete target. It does not take a range, a channel, or `latest`. It does not replace a pin with a newer minor while it checks the graph. If the composition changes, the setup’s next minor version is a different object.

A setup belongs to one harness from creation. Native implementation is a property of the component, not a field you can rewrite on the setup after the fact. Dependencies are exact version references plus a closed vocabulary of capabilities. Overlays are bounded and derived; they are not a place to hide a second graph.

The same canonical input always produces the same order, the same reports and the same package digest. That is the contract an agent can cache. A compiler that “helps” by substituting would make that digest a lie.

## Separate the gates

Three families of checks answer three different questions. Collapsing them into one Boolean is how operators lose the reason.

Schema and dependency constraints decide whether the graph is structurally valid. Duplicate paths, colliding command names, overlapping managed files, license conflicts and unresolved exact references stop the package. The MVP compiler does not perform semantic merging. If two instructions disagree, the package is blocked. Resolution belongs to the operator: choose another component, or publish an explicit derived version and check that version as itself.

Harness and platform support decide whether the target can execute the graph. A component that names no harness is compatible with every harness whose provider declares a native surface for its kind, and is refused where none does. A component that names another harness is a mismatch, not a hint. Whether the harness program is installed on this machine is not an eligibility input. An absent harness produces a row with a reason, not a missing row.

Trust and consent policy decide whether the operation is permitted. Admissible is not the same as auto-selectable. An `experimental` object with valid consent may be shown in a separate section and still must not be selected automatically. Local owned or pinned objects pass local checks and still are not marked platform-verified. Scoring, if it exists at all, cannot disable a mechanical constraint. Popularity is a last tie-breaker, not a trust line.

## Refusal is a feature

A failed gate should identify the incompatible edge or the missing consent. Stable reason codes belong to machines. The message belongs to people. Either way the operator changes the proposed plan explicitly instead of discovering an implicit substitution after installation.

Typical refusals are ordinary product behaviour:

- the object declares another harness;
- the provider has no native surface for that kind at the requested scope;
- a pin is a range rather than an exact `X.Y`;
- two members claim the same managed path;
- mandatory evidence is expired, failed, or not run;
- experimental risk was not accepted for this publisher or major line;
- the plan digest changed between approve and apply.

None of these is a prompt to “try a similar component.” Similarity is not a pin. The compiler’s job is to refuse unresolved conflict, not to invent a composition the operator did not confirm.

Constraints decide **new** installations and updates. An already installed target is not remotely disabled. It keeps running and receives a warning with the reason. There is no kill switch in the catalog. Offline clients use the last known state and report when it was checked.

## What the operator does with a refusal

Change one explicit input: the pin, the harness, the consent record, or the member list. Rebuild the proposal. Confirm it only while the snapshot is still current. Then ask the provider for a plan. Apply is a later command, bound to that plan’s digest.

Primary harnesses on this line are Claude Code, Codex and Grok Build. Pi, OpenCode, Cursor and Antigravity are beta: catalog and compatibility exist, and parts of the provider path still ask for more confirmation. An unknown harness is `undefined`. Automatic installation there is refused on purpose.

See also: [Supported harnesses](https://ai-stp.aiguild.space/en/docs/harnesses) in the help center.
