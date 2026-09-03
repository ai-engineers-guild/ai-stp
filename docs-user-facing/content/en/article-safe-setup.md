---
type: article
slug: safe-setup
locale: en
title: Build a setup without hiding its trust boundary
description: "Why author verification and component verification stay independent, and why only the harness provider writes native state."
published_at: 2026-08-12
tags: [trust, setup]
draft: false
---

An ai_stp setup is not a folder of files you hope will land in the right harness. It is the complete configuration of one harness, pinned to exact component versions, with origin and consent visible before anything is applied. The trust boundary is the product: who published the object, what the platform confirmed about those bytes, whether the operator accepted experimental risk, and who is allowed to write native state. If any of those facts is missing, the plan stops.

Mechanical checks run before agent reasoning. The CLI does not call a model API and does not ask for a model key. If a machine check rejects the operation, the answer is a refusal, not a workaround in free text.

![A visible trust boundary around a pinned setup](/content/illustrations/trust-boundary.svg)

## Two verification axes that never merge

`author_verified` and `component_verified` sit next to each other on a catalog card. They are independent facts. Neither is a synonym for “safe.”

`author_verified` means the platform confirmed the author or the namespace. It is a statement about identity, issued by platform owners after an auditable check of a GitHub profile, an organization, or an invitation. A confirmed author can still publish a bad version. Revoking the flag is prospective: it takes objects off the `authoritative` trust line and does not rewrite historical snapshots or already installed targets.

`component_verified` means every mandatory check for that exact version currently has accepted `passed` evidence. It is not issued by hand, is not derived from authorship, and does not claim that every scanner ran on the platform. A version that only carries `warning` can be published without this flag. When evidence expires, or when policy adds a required check the version lacks, the flag is cleared. The bytes stay the same.

Read evidence in that order: origin, then verification, then compatibility, then consent. A verified author does not make every component verified. A verified component does not grant permission to install it. A compatible graph does not move an `experimental` object onto the `authoritative` line.

## Trust lines are inclusion rules, not scores

Three lines decide how an object reaches a result set. They are not a popularity ranking and they are not a single Boolean.

`authoritative` is the ordinary path: verified author, verified version, complete passport, current mandatory checks, and compatibility evidence for the target. It may be offered without asking the operator to accept experimental risk. It is still not auto-installed. There is a plan, a digest and a confirmation.

`experimental` is shown only after explicit consent, in a separate section, labelled. Consent does not make the object automatically selectable. It does not migrate the object to `authoritative`, not even when the agent prefers it. A durable consent record is scoped to a publisher or an exact major line, not a global “trust everything” switch. A new major line, or a new requirement for authority, network, credentials, external endpoints or native surfaces, invalidates that record until the operator decides again.

`local_owner_or_pinned` is the operator’s own, imported or exactly pinned object after local checks. It is available offline. Local ownership does not make it platform-verified. Pinning a digest is a decision about which bytes you accept, not a request that the catalog pretend those bytes were scanned.

The absence of verified candidates is an honest empty state. It does not silently enable another line so that search always returns something.

## Only the provider writes native state

The CLI and the agent select, validate and bundle. They do not write the harness’s native files. The website owns the account and the public catalog. It displays results. It does not assemble a setup and it does not apply one.

Only that harness’s public provider writes the final state. This is not an implementation detail you can skip when the files look simple. Harnesses disagree about directories, formats, events and permission surfaces. A `skill` for Codex and a `skill` for Claude Code can describe similar work and still land on different native surfaces. A setup belongs to one harness from the moment it is created. Moving it is a new version, not a rename.

Copying files into a target breaks provenance and rollback. Before apply there is a plan, a digest, a backup and an explicit confirmation. The agent does not confirm a stale plan. The CLI does not treat `author_verified` as proof that a component version is safe. Secrets, tokens and `.env` bodies do not enter passports.

## Stop without substituting

When a policy check fails, keep the exact version and the evidence visible. Do not swap a dependency for “whatever still fits.” Do not widen consent to make the graph compile. Do not install the closest object that happens to pass. Return a refusal that names the boundary: missing consent, unverified version, harness mismatch, or a writer that is not the public provider.

The operator then changes the proposed plan explicitly. That is slower than a silent upgrade. It is also the only way a later target status can still mean what the plan claimed.

A running agent does not modify its own active target in place. Installation is a separate, digest-bound path through the provider. Recovery is a read of what a stopped operation left, not a second apply guessed from memory.

See also: [Trust and safety](https://ai-stp.aiguild.space/en/docs/trust-and-safety) in the help center.
