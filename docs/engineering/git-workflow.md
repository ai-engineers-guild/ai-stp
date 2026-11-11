---
description: "Branch integration, exact-source qualification and artifact publication."
last_verified: "2026-11-11"
---

# Git workflow

CI push branches: `dev`.

`dev` is the integration and complete source qualification branch. `main` names
an already qualified release source. Both branches are permanent locally and
remotely. Work branches use `feat/`, `fix/`, `refactor/`, `docs/`, `test/` or
`chore/`; Dependabot updates target `dev`.

## Source qualification

Pull requests run `integration`: redacted secret scanning with scanner controls,
Python/docs syntax and source contracts, non-database units, web/Desktop types
and units, and native library analysis and units. Actual CodeQL analysis waits
for processing and refuses open findings. The final `qualification` means that
the PR is eligible to integrate; it does not claim installed acceptance.

A push to `dev` runs `check`. The shared `source` workflow owns the same complete
matrix: server/database scenarios, web/browser/SDK matrices, CLI consumers,
archives, documentation image, Desktop installers, installed personal journeys
on Linux/macOS/Windows and the installed Linux corporate journey.
Its final `full-qualification` has a different name from PR eligibility. Both
wrappers refuse a failed, cancelled or skipped shared workflow. The shared gate
accounts for every owner and the exact expected skips for its selected phase.
Manual diagnosis runs the full matrix without automatic delivery authority.
Started full qualifications finish their owning checks and caches. A newer push
can replace a pending run but does not cancel one already running. The current
Dev-head check still refuses delivery of a superseded source. PR integration
cancels superseded attempts because they cannot qualify the updated PR.

Registered native experiments join the same gate through their owning reusable
workflow. Complete source checks select every registered experiment. PRs select
one when its source, compiler or automation changes. Missing or unknown owners
refuse selection. The WASIp2 experiment executes one identical component on
Linux, macOS and Windows; it does not enable a production provider backend.
Only successful push-to-Dev owners retain native dependency caches.
Linux package fixtures use the registered OSU Ubuntu archive mirror over HTTPS
with the distribution signing key. The project APT wrapper selects only its
job-local source file; it leaves runner sources, resolver and trust unchanged.
Index retrieval refuses partial failures before package installation.

The vendor-discovery owner reads the vendor's local configuration API with an
isolated profile and checksum-pinned official distribution. Codex controls cover
scope discovery, distinct same-name skills, reload, malformed-input refusal and
configuration precedence. Proof kind is vendor_configuration_read; installation
effects, runtime invocation and current authority retain their respective owners.

## Integration and delivery

1. Branch from current `dev`, implement, regenerate affected projections and run
   source checks with `just check`. Run affected execution checks on their native
   hosts. Review the diff and record exact-source evidence in the PR.
2. Commit intended paths with the existing global Git identity. Do not override
   authors or invent attribution. Merge a green, current PR into `dev` with a
   merge commit.
3. `check` qualifies that integrated commit once. Dispatch preparation with
   `just delivery-prepare SOURCE_RUN_ID`. `deploy` admits only the latest
   successful push-to-Dev run and current attempt, its unique successful
   `full-qualification`, the current Dev head and the reviewed live rules.
4. Delivery registers the three unchanged, accepted CodeQL SARIF payloads for
   the intended Main commit and reference. An authenticated GitHub upload receipt
   binds each original payload to its Dev commit, category and reference, even
   when the uploaded SARIF omits its optional provenance field. Existing
   provenance, findings, fingerprints and dispositions remain unchanged.
   Processing errors and open findings
   refuse delivery. The native Main CodeQL rule remains enforced.
5. The first delivery run prepares Main admission without changing references.
   Using the existing authorized Main administrator, run
   `just delivery-promote SOURCE_SHA SOURCE_RUN_ID SOURCE_ATTEMPT` from that
   qualified checkout. It independently rechecks source evidence, complete live
   rule actor lists, current Dev and accepted Main analysis, fast-forwards Main
   with `force: false` and reads it back. A new CLI version gets an immutable
   annotated tag and its publication workflow; an existing completed version
   dispatches deployment reconciliation. Running CLI publication is reused.
   No new credential or Actions bypass is required. A refused write ends the operation.
6. CI only advances the monotonic `deploy/prod` ref once Main already equals the
   qualified source and its CLI download is completely published. Admission checks
   the annotated release tag, source ancestry and all fourteen native payloads and
   checksum assets. The target owns the rollout; the workflow carries no host
   credential. Public verification checks the exact source, schema and service
   health. A preparation run does not claim deployment or publish installers.
7. A new Desktop version gets an immutable annotated tag and publication of the
   six installers from that successful source run. All manifests, source identity
   and SHA-256 hashes are verified before publication. The publisher executes no
   repository program, preserves existing assets and uploads only missing names
   with identical expected bytes. It can finish an interrupted draft.

Main does not rebuild the source. Client release workflows use the current Main
commit's successful Dev run. Desktop publication stages the qualified installers;
CLI publication stages the fourteen qualified archives, wheels, crate and
checksum files, attests them and uses the same publisher as Desktop. Neither path recompiles the product. The OIDC-bearing CLI
attestation job executes no repository code. Unsigned Desktop bundles retain
that disclosure; publication does not assert notarization or code signing.

A new CLI version reaches qualified Main before its release tag and attestation.
Its workflow publishes those exact archives, dispatches the existing standalone
PyPI/crates.io Trusted Publishers, and checks the actual public registry bytes.
The existing PyPI environment review remains required. Only successful registry
owners dispatch deployment reconciliation for the original qualified source run.
Until publication completes, `deploy/prod` stays unchanged. Main analysis
preparation and the explicit Main operator do not require a download that cannot
yet be published; actual deployment always does. The canonical download link matches the source package
version, so a deployed Web page cannot point to the unpublished next version.

## Admission and recovery

Rule sources live in `.github/*ruleset.json`; live GitHub rules enforce access.
Dev requires PR integration. Main requires `full-qualification` and real CodeQL
results, forbids deletion/non-fast-forward updates, and retains the existing
administrator-only Main update restriction. The built-in GitHub Actions integration cannot be registered as a ruleset bypass
actor. Hosted delivery therefore never attempts a Main write: the existing
operator is an explicit, evidence-checked step, with no alternate-credential
retry after a refusal. Existing administrator authority does not replace
qualification or code-scanning evidence.

The owner approved this arrangement in #1392: default Dev and all four reviewed
rules are active. Read back every rule, including complete actor lists, and the
default branch before promotion. The hosted controller cannot change rulesets. GitHub
may omit actor lists from its read-only response, while GitHub still
authorizes deployment writes. The operator requires the complete actor lists.
Both paths refuse other visible policy drift. Until
the four reviewed rules and default Dev are active, it changes no references.

When Main has not yet advanced, use `just delivery-promote` with the admitted
source, run and attempt. For an interrupted deployment after Main advanced,
dispatch `deploy` on Dev with the existing successful `source_run_id`. If the
operator's dispatch failed after its Main update, rerunning the same command
reuses Main, reconciles the current CLI owner and dispatches only missing work.
A failed publication retains its original run and immutable bytes for diagnosis;
it is never treated as permission to rebuild or replace an asset. Admission is repeated against
current GitHub state. Completed Main/ref/tag operations are reused; existing tags
and release assets never move.
Do not rebuild to repair publication. Correct source mistakes through a new PR
or a reviewed revert. Keep branches synchronized and remove only finished work
owned by the task.

First-party setup configuration releases with the CLI/Desktop. Historical
external-provider plans, artifacts and receipts retain their exact compatibility
route. Context selection never retargets an admitted operation. Harness
executables remain user/vendor managed through official vendor commands.
