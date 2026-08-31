---
description: "SPEC-006: Search, candidate selection, and setup compiler."
last_verified: "2026-08-26"
---

# SPEC-006: Search, Selection, and Setup Compiler

## Purpose

The agent receives a bounded set of eligible candidates and selects or adapts components explainably, while the deterministic setup compiler creates a coherent native package or blocks an unresolved conflict.

## Scope

The scope includes mechanical constraints, trust lines, search and its ordering, an optional scoring layer, an arbitrary dependency graph, bounded overlays, conflict resolution, composition and conversion reports, and a deterministic package. The agent does not replace the dependency resolver, policy mechanism, or write provider. The MVP setup compiler implementation boundary is owned by `ADR-0028`: semantic merging, equivalent selection, and composition optimization are not performed in the MVP.

Specific scoring criteria and weights belong to versioned policy and are not fixed here: the MVP must work without this layer.

## Terms

- `SelectionRun` is a frozen context of passports, questions, and candidates.
- `SelectionProposal` is a short-lived composition proposal within a recommendation session; the machine boundary is owned by `docs/contracts/selection-proposal.md`.
- `RecommendationTrace` records the trust line, consent source, and reasons for each candidate.
- `SetupGraph` contains exact nodes, dependencies, conflicts, and overlays.
- `CompositionReport` records reasons for selection and rejection.
- `ConversionReport` records the completeness and losses of native adaptation.

Trust lines under `ADR-0016`:

- `authoritative` — verified author, verified version, complete passport, current mandatory checks, and compatibility evidence;
- `experimental` — an unverified third-party object included in results only with explicit consent;
- `local_owner_or_pinned` — the user's own, imported, or exactly pinned object after local checks.

## Requirements

- `REQ-601`: Mechanical compatibility, access, trust, license, authority, and provider-support constraints are enforced before agent selection; the machine boundary for families, rejection reasons, and check order is owned by `docs/contracts/eligibility-constraints.md`.
- `REQ-602`: The `authoritative` line includes only an object with a verified author and version, a complete passport, current mandatory checks, and evidence of compatibility with the target.
- `REQ-603`: Objects on the `experimental` line are included in results only when the request has an explicit consent flag, are returned in a separate response section, and are not moved to `authoritative` either automatically or by agent decision.
- `REQ-604`: The agent retains an explainable recommendation trace containing facts, questions, and selected and rejected alternatives.
- `REQ-605`: An arbitrary graph supports exact dependencies and bounded overlays with `derived_from`.
- `REQ-606`: The setup compiler detects conflicts in paths, identifiers, versions, instructions, hooks, MCP, commands, plugins, authority, network, and licenses.
- `REQ-607`: The same canonical input always produces the same order, reports, and package hash.
- `REQ-608`: An unresolved conflict or unsupported native surface blocks the package.
- `REQ-609`: The package contains a composition report and a loss-aware conversion report.
- `REQ-610`: Deterministic search order is the mandatory result order; additional candidate scoring is optional and may be absent.
- `REQ-611`: If scoring is computed, it is decomposed by criterion, explainable, and versioned; popularity does not change trust and is used only as the final deterministic tie-breaker.
- `REQ-612`: The absence of scoring is not an error: results return `ranking: unavailable` and preserve search order.
- `REQ-613`: Neither scoring nor its configuration disables mechanical constraints, the trust line, or mandatory compatibility evidence.
- `REQ-620`: The number of candidates in a response is bounded by a declared policy limit, not a hard-coded number.
- `REQ-629`: Object eligibility is reported as one row for every harness in the closed list, not only for the named harness. Whether a harness is installed on this machine is not an eligibility input and does not inject `harness_id` into either a passport or proposal: an absent harness produces a row with a reason from `docs/contracts/eligibility-constraints.md`, not an absent row. Explicitly naming a harness may narrow the response and remains valid.
- `REQ-621`: Selection input is assembled deterministically from the developer passport, current-device passport, current-project passport, selected harness, and registry candidates; environment facts come from the device passport.
- `REQ-622`: A composition proposal is a derived, short-lived object of a recommendation session: showing proposals creates no version, target, `entity`, revision, or synchronizable registry object; the local session row stores an exact snapshot only for cross-process confirmation, staleness, and an idempotent outcome, while the user's agent decides the number of proposals within policy.
- `REQ-623`: Explicit confirmation of exactly one proposal atomically freezes its exact graph as a new private `SetupVersion` for the selected harness, records `RecommendationTrace`, and pins it as the selected version for the project-and-harness pair with state `pending_install`; installation remains a separate provider plan, and no `SetupVersion` is created without confirmation.
- `REQ-630`: A proposal with no members is created only with an explicit empty flag; without it, zero members remains a typed rejection because it is indistinguishable from a search that found nothing. An empty flag together with named members makes a false assertion about the call and is rejected rather than ignored. Confirming an empty proposal remains ordinary `REQ-623`: freezing requires a separate user decision, and the empty `SetupVersion` is immutable and installed through the provider's standard plan. An installed empty setup leaves the target managed with declared empty content, so a file appearing there is drift; this differs from uninstalling, which leaves the target unmanaged, and the verbs for the two operations are not mixed (`ADR-0124`).
- `REQ-624`: A proposal is bound to an input snapshot: changing a candidate hash, context-passport revisions, or policy version makes it stale; confirmation of a stale proposal is rejected with a typed error, while repeated confirmation of the same proposal idempotently returns the same version.
- `REQ-625`: The MVP setup compiler performs only deterministic operations: canonical ordering, deduplication of identical exact references, resolution of the exact dependency closure, merging of non-overlapping managed paths, and deterministic generation of reports and the package.
- `REQ-626`: The setup compiler does not perform automatic semantic merging, equivalent selection, or optimization for conflicting instructions, hooks, commands, MCP, agents, plugins, and settings; a semantic conflict blocks the package, resolution belongs to the agent and user through selection of another component or an explicit derived component or overlay, and the derived object is checked as a separate exact version.
- `REQ-627`: A durable consent record stores the target, scope, decision author, time, source, and authority-and-capability fingerprint; a new major line or a new requirement for authority, processes, network, credentials, external endpoints, managed paths, or native surfaces invalidates the record for that version until a new explicit decision, the result always remains on the `experimental` line, and the consent source and fingerprint are recorded in the recommendation trace and installation plan.
- `REQ-628`: Confirmation atomically stores a complete `SetupVersionPassport` and an independent canonical definition artifact with exact component refs; HarnessBundle is not used as the artifact for its own embedded passport, and incomplete legacy member metadata explicitly blocks publication.
- `REQ-614`: Consent to unverified objects is an explicit request flag and applies within a command or session; indefinite global consent to all unverified objects is not supported, while durable exceptions exist in exactly two scopes under `docs/contracts/unverified-consent.md` — publisher and exact-object major line — and are selected explicitly by the user.
- `REQ-615`: An object on the `local_owner_or_pinned` line is selected directly after local checks, is available offline, and is not marked as platform-verified.
- `REQ-616`: `RecommendationTrace` stores each candidate's line, author and version state, consent source, authority-and-capability fingerprint, mandatory-check results, and compatibility evidence.
- `REQ-617`: The absence of verified candidates does not enable another line by itself and remains an honest state.
- `REQ-618`: Candidate search uses normalized name, description, tags, and synonyms; supports prefix and phrase queries; and supports structural filters by type, harness, compatibility, source, line, `author_verified`, and `component_verified`.
- `REQ-619`: Local search works without a network, models, or a separate vector store; cloud-search unavailability does not block local search.

## Result Ordering

The order is built in three steps, and the first two are mandatory:

```text
mechanical constraints (REQ-601)
        ↓
trust line (ADR-0016)
        ↓
search order — mandatory
        ↓
candidate scoring — optional layer
```

Scoring orders candidates within a line and never moves a candidate between lines. Its absence is a normal state: the MVP must remain useful without it, so the specific set of criteria and weights belongs to versioned policy, not this specification.

Final composition selection belongs to the agent and user: the product returns eligible candidates, their line, and match signals, but does not declare the selected object uniquely correct.

Direct search and a recommendation session are distinct modes. Search remains an ordinary registry operation and creates no proposals; a session proposal becomes durable only through confirmation under `ADR-0027`.

The setup compiler must detect: a required-dependency cycle, a missing exact reference, a hash mismatch, incompatible versions of one component, two owners of one managed path, duplicate identifiers for commands, agents, MCP, and plugins, conflicting instructions and precedence, incompatible hook ordering, loss of a required native surface, a path or reference escaping the package, an undeclared required environment or external endpoint, authority escalation, prohibited redistribution, missing entitlement, an `experimental` candidate without consent, an unsupported OS/harness/provider combination, and provider rejection by `validate-bundle` or `plan-bundle`.

Composition and conversion reports remain deterministic reports: they explain selections and losses but are not a reasoning mechanism and do not change the composition.

## States and errors

`SelectionRun` moves through the states `created`, `needs_input`, `filtered`, `ordered`, `composed`, `confirmed`, `blocked`, and `cancelled`; confirmation freezes the version atomically under `docs/contracts/selection-proposal.md`. The setup compiler returns typed conflicts and does not create a partial package. The absence of verified candidates is the normal `no_candidate` state, not a server error or grounds to enable another line.

Local search distinguishes `available`, `empty`, and `degraded`; cloud-index unavailability yields `degraded` with the last check time, not an empty successful result.

## Security and privacy

The model receives only the necessary structured summary, not secrets or complete private source code. The agent cannot reintroduce an excluded reference through free text. An overlay does not bypass license, access rights, or provenance. Resource limits constrain graph size and compilation time.

## Compatibility and migration

The scoring version, setup compiler version, and input hash are recorded in the recommendation trace. Changing weights does not alter an already frozen personal version. A new provider contract is applied only after a compatible native converter and contract checks are available.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-601` | A property test proves that an excluded candidate is never selected. |
| `REQ-602` | Negative trust tests exclude an incomplete object, unverified author, unverified version, and stale evidence from `authoritative`. |
| `REQ-603` | A request without consent does not return `experimental`; a request with consent returns it in a separate section; and the agent cannot move such a reference into the automatic composition. |
| `REQ-604` | The golden trace links the decision to passport facts and rejection reasons. |
| `REQ-605` | Graph tests cover dependencies, overlays, and exact provenance. |
| `REQ-606` | Adversarial fixtures cover every conflict class. |
| `REQ-607` | Repeating one input produces a byte-identical complete `ai-stp-bundle/1`, identical logical/artifact digests, and matches the literal golden oracle. |
| `REQ-608` | An unresolved-conflict test creates no package. |
| `REQ-609` | Contract validation requires both reports and loss states. |
| `REQ-610` | Results without the scoring layer preserve deterministic search order and remain usable. |
| `REQ-611` | A golden scoring fixture verifies each criterion's contribution and the policy version. |
| `REQ-612` | Disabling the scoring layer yields `ranking: unavailable`, not an error or empty results. |
| `REQ-613` | Configuration tests do not allow evidence to be zeroed, the line to be changed, or constraints to be bypassed. |
| `REQ-614` | Consent from a previous command or session does not affect a new request, a clean profile does not return `experimental`, and the `publisher` and `object_major` scopes cover different candidate sets in fixtures. |
| `REQ-615` | An offline fixture selects the user's own object and does not show it as platform-verified. |
| `REQ-616` | The golden trace contains the line, author and version state, consent source, authority-and-capability fingerprint, and evidence for each candidate. |
| `REQ-617` | Empty `authoritative` results do not mix in candidates from other lines. |
| `REQ-618` | Search fixtures cover prefix and phrase queries and every structural filter. |
| `REQ-619` | Search with the network disabled returns local results and `degraded` for the cloud part. |
| `REQ-620` | Changing the policy limit changes result size without a code change. |
| `REQ-629` | A fixture for a machine missing one harness retains its row in the matrix with a reason; an object with a layout for only one harness does not become eligible for another; explicit narrowing leaves exactly the named rows. |
| `REQ-621` | The golden selection fixture uses the device passport for environment facts, and replacing the device changes candidates without changing the developer passport. |
| `REQ-622` | Cancelling a session and showing one or more proposals create no version, target, `entity`, revision, or sync event; the session row does not enter the entity graph and stores the terminal outcome idempotently. |
| `REQ-623` | Confirmation creates the version, trace, and pin atomically, while an injected persistence failure leaves none of the three. |
| `REQ-630` | A call with no members and no empty flag is rejected; with the flag it creates a zero-member proposal; the flag together with a member is rejected; a confirmed empty version is immutable and passes provider planning, application, and restoration. |
| `REQ-624` | A fixture with a changed candidate or context passport rejects confirmation with a typed error; an injected change between preflight and the write lock proves revalidation and complete rollback, while repeated confirmation returns the same version without a second object. |
| `REQ-625` | Recompiling one input produces the same complete ZIP with its passport, both reports, and exact files, while the composition report lists applied operations only from the allowed set. |
| `REQ-626` | Fixtures with conflicting instructions, hooks, and settings block the package without attempting a merge, while an explicit derived overlay passes only after its own checks as a separate version. |
| `REQ-627` | Fixtures for a new major line and expanded authority reject the old consent record and require a new decision, while the record never moves a candidate to `authoritative`. |
| `REQ-628` | A test validates the stored revision with the `SetupVersionPassport` model, reads definition bytes by artifact digest, and uses an injected failure to prove joint rollback of content/version/trace/pin; complete and legacy aggregates are distinguished by an explicit flag. |
