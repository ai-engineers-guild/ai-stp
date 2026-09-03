---
description: "SPEC-008: Providers, installation and recovery."
last_verified: "2026-09-02"
---

# SPEC-008: Providers, installation and recovery

## Purpose

`ai_stp` transfers the verified package to the only public provider of the selected harness. The provider securely manages the runtime, target directory, backup, application, startup, and recovery.

## Scope

Includes seven public setup managers `NDDev-OpenNetwork/*-setup-system` - one for each harness of the closed set `ADR-0120`: claude-code, codex, cursor, opencode, pi, grok-build and antigravity - release artifacts, common protocol, runtime lifecycle, external package, inactive target directory, plan, application, state, recovery and import of an existing native configuration.

The previous estate of providers has been removed (`ADR-0119`, `ADR-0120`). It remains in historical ADR as context and is not the source for a new object; the trust line is assigned `provider-policy.toml` to the family `*-setup-system`.

The closed authoring loop of setup systems is a check and coordination loop: it is not cloned to the user, is not a dependency or source of runtime behavior, and does not participate in the operation of the application. Direct writing of `ai_stp` to native directories is prohibited.

## Terms

- `ProviderRelease` - signed exact artifact of the public manager of the setup.
- `HarnessBundle` - limited native package from the setup compiler.
- `HarnessTarget` - isolated root of the executable environment and configuration.
- `BackupRef` — link belonging to the provider; bytes are not stored in the `ai_stp` database.
- `ImportedSetup` is a personal setup created from an already existing native configuration.

## Requirements

- `REQ-801`: Providers are delivered as versionable release artifacts rather than working Git submodules. Installation using the v3 protocol requires a private release manifest - signed by Ed25519 or linked by the consumer from attested bytes and the assigned rule `build_attestations`; a provider without it is installed only by an explicit separate option, and the plan reports such an installation as unverified. The changing path is limited by this rule, the observing provider calls are not.
- `REQ-802`: All seven closed set providers implement a common versioned protocol core and machine-readable `provider-info`; product-specific software lifecycle and launch are declared capabilities, not fictitious required commands. The announcement differs by product and this is not a defect: on `0.0.4`+ six announce `software_install` / `software_update` / `software_remove`, `pi` does not announce any, and antigravity announces three and does not announce `launch`.
- `REQ-803`: The provider has sole ownership of native projection, locks, staging directory, target change, backup, state and restore; he owns the program and launches only with an explicitly declared capability.
- `REQ-804`: Package checking disallows absolute and parent paths, directory escaping, symbolic and hard links, special devices, normalized path repeat, and exceeding limits.
- `REQ-805`: The plan has no side effects and is bound to the current target hash, provider and environment versions, and expiration date.
- `REQ-806`: The application requires an exact hash of the plan, a lock, and re-validation of the target after acquiring the lock.
- `REQ-807`: A backup is created before the first change, and the unmanaged state is retained by contract.
- `REQ-808`: The new target directory remains inactive until verified, ready to run, and status checked.
- `REQ-809`: The states of `applied_unverified`, `verified`, `partial` and `failed` differ as a result of the provider and durable operation; Only `verified` is called success.
- `REQ-810`: The current agent session does not overwrite its own active target directory in place.
- `REQ-811`: The provider's release is accepted only after checking the committed trust policy, signature, source, artifact hash, whether the release belongs to the committed list of approved releases, and the rollback protection sequence. The list is secured by digest together with `provider_id` and `repository`, who have the right to present it; an empty list does not allow anything.
- `REQ-812`: Rekeying and revocation changes release validity without rewriting historical evidence or automatically deleting the target; recovery requires a separate verified plan, an exact digest from the local verified history and does not go below the policy floor.
- `REQ-813`: Import of an existing configuration is performed in the order of inspection without modification, backup of the provider, clearing of secrets and inventory, creation of a personal setup with a passport, exact file hashes and origin, local verification and fixation in the registry.
- `REQ-814`: `BackupRef` and `ImportedSetup` remain separate objects; a link to a backup copy is not the identity of the setup and does not replace it.
- `REQ-815`: The imported setup contains only the names of the required environment variables; secret values ​​from the native configuration are not transferred.
- `REQ-816`: Installation when a required environment variable is missing is allowed with a warning, and launch readiness remains `needs_configuration` until it appears.
- `REQ-817`: Harness version belongs to the managed lifecycle of the provider; `ai_stp` does not update or replace the Harness program past it.
- `REQ-818`: A change to the program or target of Harness outside the provider is detected as `local_drift` and is not automatically resolved.
- `REQ-819`: The object declares the need for credentials and external authorization before installation; values, keys and addresses of their issue are not included in the passport.
- `REQ-820`: Setting up an object with a declared access need explains to the user each required authorization and guides the configuration; the installation may complete, but launch readiness remains `needs_configuration` until the exact provider observes a matching authorization type in the `ready` state; absence of evidence, mismatch of species and unknown form are not considered ready.
- `REQ-821`: Frozen protocol v1 does not state network isolation; the network demand is introduced only by a separate version of the protocol and takes the private values ​​`none`, `artifact_download` or `runtime_external` for each action.
- `REQ-822`: The protocol v2 result reports `network_enforcement` as `enforced`, `unavailable` or `not_requested`; the value `unavailable` is not called network prohibition.
- `REQ-823`: Action with `network_requirement=none` is launched only after the proven capability result `enforced`; the lack of a proven mechanism on the current or future OS returns a typed failure before the provider starts.
- `REQ-824`: The `artifact_download` permission belongs to a separate download phase and does not extend local verification, target change or subsequent actions; `runtime_external` is only allowed to be run explicitly.
- `REQ-825`: `install plan` passes one complete content-addressed HarnessBundle to `validate-bundle` and `plan-bundle`; provider validates the format, logical digest, raw artifact digest, size, and current target digest before creating the modifying operation.
- `REQ-826`: Confirmed immutable plan binds both HarnessBundle identities, size and exact provider plan digest; internal plan digest `ai_stp` does not replace provider plan digest.
- `REQ-827`: Before `apply-operation`, the consumer re-checks the exact cached bytes and passes the original target and provider plan digests; the exact response `stale` after a provider-side lock - including `state=refused` with `reason=stale` - is stored as a failure with no effect, a mismatched response after a possible effect creates `partial`, and `resume` observes `provider-info`/`status`, if necessary calls only `recover-operation` and never repeats apply. `apply-operation` is checked against `plan_digest` and `expected_target_digest`; four bundle-echoes remain required for `validate-bundle` and `plan-operation`. `status` after install proves `state=managed`, protocol/provider identity and clean/verified drift; additional provenance fields are checked only if the provider sent them.
- `REQ-828`: Conformance checks validation and plan on literal content-addressed ZIP corpus with exact binding, but does not run modifying or executing commands on the user target; such commands are only proven by individual E2Es on a one-time target.
- `REQ-829`: Repeat scheduling with the same logical idempotency key returns the currently active operation; after the terminal `stale`, `cancelled`, `partial`, `failed`, `rolled_back` or `verified`, the key is atomically transferred to the new operation without reopening or deleting the old log.
- `REQ-830`: History of installed versions and rollback follow the serialized order of verified events; The coincidence of wall-clock timestamps and the creation order of the operation cannot rearrange the current and previous versions.
- `REQ-831`: Frozen protocol v1/v2 are not expanded; protocol v3 separates the mandatory setup/bundle command core and closed capability-negotiated operations, and unknown/unsupported operation is rejected until the plan and target change.
- `REQ-832`: Prepared exact graph and composed graph after finalization create one immutable `SetupDefinition` and use one HarnessBundle, provider plan and common confirmation, apply, state, copy, restore and delete paths.
- `REQ-833`: Precise provider projection profile declares component and projection views, native identifier spaces, bundle formats, limits, OS/architecture and digest; compiler and provider independently reject an unsupported component, surface, collision, or profile change.
- `REQ-834`: `plan-operation` is clean and bundles operation, provider build, verified consumer release digest/protocol, target snapshot, optional exact bundle/BackupRef, permission profile, platform/runtime identity, term and effects; `apply-operation` requires an accurate plan artifact/digest and re-checking after acquiring the lock.
- `REQ-835`: Permission/execution profile is not a setup identity and does not change SetupDefinition/component graph digest; standalone legacy identities migrate only in a confirmed mutation after a backup.
- `REQ-836`: Provider state and backup metadata link exact SetupVersion, SetupDefinition, components, bundle, projection profile, provider plan/release, target and native ownership; `status` does not migrate state, and secret values are not preserved.
- `REQ-837`: Provider v3 conformance is distributed as an immutable public artifact with no runtime dependency on private `ai_stp` or authoring loops and includes schemas, canonical examples, hostile corpus and expected digests.
- `REQ-838`: Software download is allowed only in a separate phase; subsequent local apply again requires proven network isolation, and launch uses only the explicitly declared `runtime_external` capability.
- `REQ-839`: Provider durable journal has closed phases `prepared` and `committed`, binds exact plan/operation/target-bound BackupRef and blocks the new plan until recovery; prepared restores the exact pre-operation target, committed only checks the result and drains cleanup.
- `REQ-840`: The conversion report links the component view, native surface and projection view; each exact component owns non-empty content, and the provider's native syntax and required tree markers are checked before the plan without changing the target.
- `REQ-841`: Import first builds a deterministic read-only plan with respect to exact inspection: natural native boundaries become proposed components, the hash of a set of files is not passed off as a digest of an artifact that has not yet been materialized, and a file that could not be read remains an explicit blocker. A file exceeding the declared size limit is read and hashed: it is excluded from the proposed components and is not a plan blocker. A path refused as a symlink, reparse point, hardlink or special file is reported per file with its reason and is likewise excluded rather than silently skipped. One path cannot be considered both excluded and blocking at the same time. Component boundaries come from the harness catalog — the same owner discovery consumes — and a file matching a declared-key layout becomes a contribution candidate whose artifact carries only the extracted key value. Registration of setup and its exact component graph is performed as a separate confirmed action and rejects the changed inspection; it is complete by default, refusing a plan that excluded anything until an explicit partial mode is named, and a partial registration records the mode and the exact excluded paths in the setup passport.
- `REQ-842`: The purchased public SetupVersion does not contain the local project identity. `install plan --setup` accepts an explicitly named project root, requires its current developer/device/project revisions, and associates an exact setup graph with the computed local context snapshot without changing the published passport.
- `REQ-843`: Read-only diff of a local discrepancy compares only managed paths of the exact HarnessBundle from the last verified operation with the saved provider target, does not follow links, does not change the target and reports stable classes `modified`, `added`, `deleted` without absolute paths; the absence of exact evidence is indicated separately and does not trigger recovery.
- `REQ-844`: Provider release trust has closed levels `verified_publisher`, `signed`, `build_attested` and `unverified`. `verified_publisher` requires both verified exact bytes and a publisher previously assigned by local policy as verified; a remote checkmark or account name alone does not give trust to the bytes.
- `REQ-845`: `build_attested` requires a successful Sigstore/GitHub artifact attestation on the actual uploaded artifact with exact repository, source commit and signer workflow from local policy. Manifest, workflow output, and predicate do not extend the policy; the absence of a verifier, network, or offline bundle results in a typed failure, rather than a downgrade to a trusted state.
- `REQ-846`: The trust level, identity attestation and digest of the used bundle are included in the immutable install plan, re-checked before apply and stored in the local history. The repeated check feeds the `gh attestation verify --bundle` Sigstore bundle extracted from the saved JSON GitHub CLI response, rather than the `attestation` wrapper with `bundle_url`. The compatible field `provider_release_trusted` is output as `level != unverified` but is not a level source.
- `REQ-847`: The consumer materializes the private release manifest from the attested artifact, exact tag, source commit, and `provider-info` of these bytes when the publisher did not include JSON. Sequence is encoded from the exact semver tag. This is not a second trust anchor and does not add bytes to `releases`. The executable file does not run until the attestation check is successful.
- `REQ-848`: The setup plan names the selected setup - its name and its own description - along with a list of effects. The list of effects is specific to the files the provider will record and says nothing about what it means to change them; for a setup whose content is disabled, these are different questions. The description is taken from the exact SetupVersion passport, which the plan already allows, and is not abbreviated.
- `REQ-849`: A provider executable delivered as a Python distribution is accepted through provenance, never through the channel (`ADR-0141`). The distribution carries the native binary as package data at a stable relative path and carries no release manifest: the consumer materialises one from the facts its verification proves, as it already does for an attested GitHub release, with `signing_key = "attested"` and an empty signature. The materialised `entry_point` names the packaged binary; a console-script entry is refused, because it is a shim and the digest and name checked here must belong to the bytes that run.
- `REQ-850`: Before such a binary runs, the index's PEP 740 provenance for that exact file is fetched and its Sigstore bundle verified over the file digest. The publisher triple — repository, workflow, environment — is matched against locally pinned policy carrying the same fields as `build_attestations`, and only a match reports `verified_publisher`. The channel earns an existing level; it does not introduce one.
- `REQ-851`: A missing provenance document, a bundle that does not verify, a publisher outside policy, and an index that serves no provenance are one outcome, `unverified`, not four gradations. With no index publisher rule pinned, every distribution-delivered provider is `unverified`, which is the behaviour that predates this requirement, so the absence of policy is the rollback.
- `REQ-852`: `ai-stp-bundle/2` binds one exact provider profile and one exact scope adaptation per component under `ADR-0144`. The compiler and provider independently reject a missing binding, profile/scope mismatch, unbound owner, path outside its adaptation, changed projection artifact, or component passport mismatch before an operation plan exists. The staged `/1` path stays byte-identical until every provider advertises `/2`, then is removed before the first supported release.

## States and errors

The provider operation distinguishes between `planned`, `stale`, `applying`, `applied_unverified`, `verified`, `partial`, `failed` and `rolled_back`. The lapse of time after a possible side effect is not repeated blindly. A parallel change returns a lock or target conflict. A restore error preserves the last accurately confirmed state.

## Security and privacy

The provider is triggered by a precise array of arguments with `shell=false`, a filtered environment, and a time and output limit. Protocol v1 does not promise network isolation. Protocol v2 executes `network_requirement=none` only through a proven launcher and fails if the capability is not available. The release artifact is verified against the trust policy. The package does not contain arbitrary scripts or secrets. The privilege escalation password is never passed to the agent or CLI.

## Compatibility and migration

The version of the contract is agreed upon before the operation. The old provider does not accept the new incompatible packet scheme. The public implementation, private compliance check, release artifact, and consumer manifest are promoted separately in the established cross-repository order.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-801` | Installation verification is obtained by the provider from the release manifest without Git cloning; `install plan` under protocol v3 without a manifest is rejected and calls `provider fetch`, a closed manifest and an explicit unverified; with an explicit parameter plans and reports `provider_release_trusted` equal to `false`, and the manifest along with this parameter is rejected as a contradiction; v1 plans without a manifest as before. |
| `REQ-802` | The semantic compliance check compares `provider-info` with the actual CLI actions of all seven providers. |
| `REQ-803` | A negative check proves that there is no direct target entry from `ai_stp`. |
| `REQ-804` | The set of malicious packages covers all classes of paths, links, devices and limits. |
| `REQ-805` | Checking the snapshot confirms that there have been no changes since the plan was built. |
| `REQ-806` | A changed target and a changed plan hash will block application. |
| `REQ-807` | Failure checks confirm pre-write backup and retention of unmanaged data. |
| `REQ-808` | A status or ready to run error does not toggle the active pointer. |
| `REQ-809` | The failure matrix checks all long-lived states of the result. |
| `REQ-810` | End-to-end verification confirms the current session until the next launch. |
| `REQ-811` | Benchmark signature and manifest checks reject unknown key, policy mismatch, modification of any signed field, exact executable bytes mismatch, and rollback; a correctly signed release outside the assigned list and approved bytes under someone else's `provider_id` are rejected by the code `release_not_pinned` before the first launch of the provider; trusted plan repeats the check before apply and atomically advances history only with `verified`. |
| `REQ-812` | Fixtures for changing and revoking keys check overlap and blocking; recovery only accepts a separate confirmed plan for exact digest from verified history and does not reduce floor. |
| `REQ-813` | The fixture of an existing target undergoes inspection, copy, cleaning, inventory, passport, verification and fixation without changing the target. |
| `REQ-814` | Deleting an imported setup does not delete the backup copy, and vice versa. |
| `REQ-815` | The native configuration with secrets provides a passport with only variable names. |
| `REQ-816` | Installing without a variable completes with a warning and running returns `needs_configuration`; readiness takes the required names from the exact selected SetupVersion even without a CLI flag, and the hostile input `NAME=value` is rejected without reflecting the value in the machine output. |
| `REQ-817` | A negative check proves that there is no Harness update path past the provider. |
| `REQ-818` | The fixture of a program modified outside the provider gives `local_drift` and does not run the fix itself. |
| `REQ-819` | The object fixture with credentials shows the sign before installation and does not contain values ​​and addresses. |
| `REQ-820` | Exact SetupVersion shows the requirement in the install plan; the provider status fixture checks `missing → pending`, matched `ready → installed`, revocation `ready → pending`, and the unknown form and mismatched form are rejected without leaking values. |
| `REQ-821` | Contract check saves wire shape and default conformance v1 without network fields; explicit v2 conformance closes the commands, phases, and requirements dictionary and rejects the unknown version. |
| `REQ-822` | The decision matrix prohibits passing off `unavailable` as `enforced`, requires launcher identity and evidence for an enforced claim, and preserves observable evidence. |
| `REQ-823` | `provider network --json` reports observed capability; v2/v3 lifecycle on the current Linux x86_64 release profile tries DNS, IPv4 and IPv6 connections, and the `none` action either provably blocks them or does not fire; any other OS without a proven launcher fails closed. |
| `REQ-824` | Conformance fixture proves that the allowed download phase is launched separately, and apply of the same action again passes only through the proven launcher. |
| `REQ-825` | The end-to-end CLI fixture checks the literal ZIP path and the exact argv validate/plan; changing any echo blocks the creation of an operation plan. |
| `REQ-826` | Changing each bundle/provider-plan field changes the user-approved plan digest, and repeating identical read-only provider answers returns the same operation. |
| `REQ-827` | Damage to cache blocks provider spawn; exact `stale` and `state=refused`/`reason=stale` leave terminal failure without recovery, mismatched apply echo leaves `partial`; a regular resume trace contains only `provider-info` and `status`, a recovery trace adds exactly `recover-operation` and does not contain apply. The test accepts apply without four bundle-echo and `status` with nested `provider_state.drift_state=clean`. |
| `REQ-828` | The corpus materializes a separate ZIP for each hostile class, checks the exact argv/echo and removes bytes after the run; trace conformance does not contain install/update/remove/apply/restore/launch. |
| `REQ-829` | Sequential and eight-thread tests after the terminal outcome create exactly one new operation, save the old log and return a new operation to repeat the active request. |
| `REQ-830` | Two pre-created operations are completed in reverse order with the same timestamp; status selects the last completed one, and rollback selects the immediately preceding verified event. |
| `REQ-831` | Contract tests preserve command/state declarations v1/v2, check closed v3 core/operations and prove non-mutating failure of an undeclared operation. |
| `REQ-832` | Prepared and composed fixtures with the same exact graph give the same SetupDefinition/HarnessBundle digests and pass the same trace validate/plan/confirm/apply/status. |
| `REQ-833` | Change profile digest, unknown component/native surface, duplicate normalized path/native ID and ownership collision are rejected before the provider plan is created and do not change the target. |
| `REQ-834` | Changing every plan-bound, expiry, or target field after lock fails without effect; timeout after a possible effect is saved as `partial` without blind retry. |
| `REQ-835` | Profile-only switch saves setup/component digests; Codex legacy safe/full-auto stamps migrate deterministically after backup and status shows setup/profile separately. |
| `REQ-836` | Install/no-op/replace/backup/restore/remove E2E saves and verifies exact provenance; read-only status leaves legacy fixture byte-identical, secret-pattern fixture is rejected. |
| `REQ-837` | A pure public-provider checkout checks immutable kit digest and conformance without access to private repositories; private root repeats exact release E2E. |
| `REQ-838` | Network trace allows download only of the exact software phase, requires enforced local apply, and allows runtime external only to the declared launch. |
| `REQ-839` | Fault-injection interrupts prepared and committed phases; status reports recovery state, the new plan remains a pure failure, exact restore/cleanup are completed with one recover command. |
| `REQ-840` | Five provider fixtures reject invalid projection kind, malformed JSON/TOML, empty component and trees without `SKILL.md`, `plugin.json` or `package.json` before mutation. |
| `REQ-841` | Repeating one inspection gives the same plan digest; changing the file changes inspection and plan digest; skill tree is grouped by one component, catalog-declared surfaces classify to their declared kinds and a declared-key host yields a contribution whose artifact holds the scrubbed key value only; an unreadable file blocks registration, a symlink or hardlink is refused per file, an oversized file is excluded without blocking the plan, complete registration over any exclusion is refused until the explicit partial mode which records mode and paths, and the plan writes neither registry nor target. |
| `REQ-842` | The test acquires a public setup with empty `facts`, fails without `--project`, then associates it with the registered project root and receives a snapshot that changes with the new project revision. |
| `REQ-843` | The verified operation fixture changes, adds and deletes files within managed roots; `target diff` returns relative paths and exact digest evidence, ignores unmanaged roots and links, leaves the target byte-identical, and the lost bundle reports `unavailable`. |
| `REQ-844` | The matrix of four levels proves the order and conditions: verified publisher without checking exact bytes is not accepted, verified bytes without an assigned publisher remain `signed` or `build_attested`, and an explicit unverified plan remains possible only with separate consent. |
| `REQ-845` | `gh attestation verify --format=json` fixtures only accept exact artifact, repository, source digest and signer workflow from policy; changing each binding, missing verified timestamp, self-hosted runner, or process-driven field instead of certificate claim fails before provider spawn. |
| `REQ-846` | Changing the level, attestation identity or bundle digest changes the plan digest; apply repeats the exact bytes and evidence checks, while history and machine output keep the level without secrets. A separate test confirms that `verify_stored` fetches the Sigstore bundle from the JSON GitHub CLI and fails if `--bundle` is left with a wrapper without `dsseEnvelope`. |
| `REQ-847` | The `provider fetch` fixture, after successful GitHub attestation, writes a private JSON, which `verify_attested` accepts; `provider-info` is called only after attestation; tag `latest` and open pre-release are rejected; the bytes do not end up in `releases`. |
| `REQ-848` | The plan of the selected setup carries its name and full description; a qualified description retains the disclaimer, not just the first phrase. |
| `REQ-849` | A wheel carrying only the binary yields a materialised manifest whose `entry_point` is that binary and whose signature is empty; a wheel offering a console-script entry is refused, and the fixture proves the refusal is over the entry shape by keeping every other field equal. |
| `REQ-850` | A provenance document verifying against a pinned publisher raises the level to `verified_publisher`; the executable does not run before the verification completes, measured the way the GitHub path is measured — by ordering the spawn after the check and failing the fixture when it is reordered. |
| `REQ-851` | Four fixtures — absent provenance, a bundle that fails verification, a publisher outside policy, an index answering 404 for every file — each report `unverified`, and each runs beside a passing control in the same test, so a check that accepted everything would fail rather than pass silently. |
| `REQ-852` | Golden `/2` vectors bind profile, scope and sorted component adaptations; changing or removing each identity, owner and member path produces its named refusal before serialization, `/1` golden bytes remain unchanged during rollout, and released-provider conformance later repeats every negative vector before `/1` is deleted. |
