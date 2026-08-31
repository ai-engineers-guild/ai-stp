---
description: "Verifiable disposition of findings from the current CLI, CI, and integration audit."
last_verified: "2026-08-16"
---

# Audit Findings Remediation Status

This document records the live status of mechanisms, not a snapshot of branches or a CI run. It does not
copy the SHA, test count, or state of GitHub issues. The `implemented` status means
that the change and local regression protection are in the current tree; it does not
replace the external evidence identified in the last column.

Permissible dispositions match the handoff contract:

- `confirmed` — the original finding reproduced without changing the meaning;
- `modified` — the check clarified the scope, risk, or required correction;
- `rejected` — the finding has been refuted by precise counter-evidence;
- `blocked` — requires someone else's system or authority for checking or fixing.

## Matrix

| ID | Disposition | Current status and local proof | Remaining gate and owner |
| --- | --- | --- | --- |
| `RVR-P1-001` | `confirmed` | The issue was reproduced on the shared machine `nddev-amsterdam`, where PR checks and deploy shared a single domain. Separation is now an environment property rather than a label schedule: checks occur on a disposable VM (`ADR-0080`), deployment — on the target host runner with an exclusive label (`ADR-0099`), release — on different disposable workers (`ADR-0101`). Three old registrations were removed on 2026-08-16; one permanent runner remains in the repository. Checked by `test_deploy_hardening.py` and `test_release_candidate.py`. | Closed. Negative probe between two live machines is no longer applicable: there are only two machines at the moment of the job, and the second is destroyed along with it. Instead, a contract test is enforced, preventing any other workflow from using the production host label. Owner: repository operations, as the owner of the closure record. |
| `RVR-P2-002` | `confirmed` | Contrary to what was here before: `check` **is canceled** by a new push on all events, because there is no deployment in it anymore and nothing to interrupt. The deployment itself is serialized — `deploy.yml` holds `cancel-in-progress: false`, and an interruption between transfer and health check would leave a state that no verdict describes. Remote marker, lock, and deterministic recovery are covered by fault tests. | Rehearsal of interruption on a dedicated staging runner is impossible and not needed: there are no tiers (`ADR-0084`). It remains to observe the first real run of `deploy.yml`. Owner: repository operations. |
| `RVR-P2-003` | `confirmed` | The finding was resolved by removing the item rather than enhancing protection: according to `ADR-0099`, CI does not open any connections to the host. A long-lived key, pinned `known_hosts`, run-scoped directory, and `deploy/cleanup-ssh.sh` were removed; `test_deploy_hardening.py` checks that the executable part of `deploy.yml` contains neither `ssh` nor `known_hosts`. | Remove unused secrets `AI_STP_DEPLOY_*` after the first successful deployment. Owner: repository operations. |
| `RVR-P2-004` | `confirmed` | The internal probe is separated from `verify_public.py`; the external verifier uses standard DNS, strict TLS, and checks commit/environment/schema. The job `verify-public` runs on `nddev-linux-standard` — physically on a different network, a different continent, and under a different infrastructure owner than the host. | Observe it during the first green deployment: before 2026-08-16, no run reached this job. Owner: repository operations. |
| `RVR-P2-005` | `modified` | There has been no `dev` branch since 2026-08-15. The deployment source has been narrowed and is explicitly checked: `workflow_run` of completed `check`, `conclusion == success`, `event == push`, `head_branch == main`, and checkout of the exact `head_sha`, not where `main` currently points. | Enable native branch/ruleset protections according to `#188` when the organization's plan allows. The protected staging environment is excluded from this line: no tier (`ADR-0084`). Owner: repository operations. |
| `RVR-P2-006` | `confirmed` | Closed: server contract in the mainline. `#366` merged on 2026-08-16 and brought in the server halves `#300`, `#302`, `#303`, and `#312`; the `dev` branch through which this transfer was planned no longer exists. The dated analysis of the transfer was deleted on 2026-08-29 along with six other completed work plans: it described the course of the merge, not an active requirement. | Closed by merge `#366`. Owner: platform track, as the owner of the closure record. |
| `RVR-P2-007` | `confirmed` | CLI and contract expect verified artifact bytes, and the server route exists: `#212` closed, and `#312` bound exact bytes to the merge publishing plan `#366`. | CLI fetch/cache/offline E2E against the deployed environment. Owner: CLI track. |
| `#180 sync` | `modified` | Contract, wire models, diagrams, and fixtures in the main line; CLI carries transport, durable cursor/journal, and merge. Half of the criterion is mocked and covered by executable tests: rewinding two devices with divergence and merging, version collision, resumption after an unknown result, tombstone, and rollback on a tampered page. | The same five scenarios executed with real commands against a deployed environment. The form is an executable script in `release_scripts/` following the example of `verify_live_slice.py`. Owner: CLI track. |
| `#170/#171 providers` | `modified` | Claude Code and Codex have immutable protocol v3 releases, signed manifests, public/closed conformance, and a full disposable-target lifecycle; exact commits, tags, and digests no longer live in a separate snapshot: it was deleted on 2026-08-28 along with the retired estate it described. The live source is `provider-policy.toml` and the slice `just evidence-providers <tag>`. | Record evidence in issues and repeat the main lifecycle on the final CLI release-candidate SHA. Owner: CLI/provider track. |
| `RVR-P2-008` | `modified` | The manual macOS workflow remains an honest future oracle, but according to the accepted `ADR-0062`, macOS is not included in the current release matrix and is not called supported. | The current gate is closed with an explicit Linux-first profile; a separate macOS run is needed only before future expansion of the support matrix. Owner: product/repository operations. |
| `RVR-P2-009` | `modified` | ADR-0047 and protocols v2/v3 define a closed requirement/result; the lifecycle goes through a proven Linux Bubblewrap launcher with refusal up to spawn when unavailable. All five real provider releases passed signed effect evidence. Frozen v1 is not issued as isolated. | Repeat the enforcement-or-refusal corpus on the final CLI release candidate before closing `#184`. Owner: CLI/provider track. |
| `#184 corpus` | `modified` | The Builder separately rejects path traversal, links, special files, secrets, modes, and limits. The Corpus provider checks filesystem and process boundaries; v2/v3 add Linux network denial-or-refusal only via a root-owned non-overwritable Bubblewrap chain. Five real provider releases went through signed lifecycle evidence. | The catalog publication path is closed along with `#181`; the CLI part requires a final RC repeat run. Owner: CLI/provider track. |
| `#167 HarnessBundle` | `modified` | The compiler preserves the exact source bytes in the deterministic `ai-stp-bundle/1` ZIP, includes the SetupVersion manifest and both reports, and returns logical/literal digests; the golden oracle compares the entire container. | Repeat the literal oracle on the exact Linux release candidate and link the artifact with each real provider plan/apply. macOS according to `ADR-0062` does not block. Owner: CLI/provider track. |
| `#185 release` | `modified` | The unpublished candidate compares five wheel/sdist pairs twice, checks metadata/licenses, creates a deterministic SBOM, manifest, and checksums. Build and OIDC attestation are separated by privileges and, from 2026-08-16, executed by different one-time workers (`ADR-0101`) — before that, both jobs addressed roles that did not exist, and the workflow could not be deployed at all. Upload authority is absent. | Make the repository public, enable protections and PyPI environment, obtain Linux clean-install evidence; publication requires a separate permission. Owner: release operations. |
| `#172 trust` | `modified` | The release manifest contains an Ed25519 signature of the canonical bytes; the private TOML policy anchors the offline public key and the exact digests of five immutable releases. The trusted plan re-verifies the executable, binds the manifest to the operation digest, and advances the append-only floor only after `verified`; the current lifecycle has confirmed floor `1`. | After the exact-head merge, perform a key-rotation/recovery drill; macOS is not included in the current support matrix. Owner: CLI/provider track. |
| `RVR-P3-010` | `confirmed` | CLI SQLite owners are closed; mandatory `back-resource` turns both warning forms into errors and checks stable FD count during repeated in-process commands. | Keep gate mandatory on Linux release profile. Separate platform logging-handler leak is passed to platform track and does not weaken CLI gate. Owner: CLI track; for separate leak — platform track. |
| `RVR-P3-011` | `confirmed` | `implementation-roadmap.md` separates the finished core from external evidence; `test_implementation_status.py` links phases 2–7 with the command registry and records the completed `#86`. | The issue owner updates the text of `#189`; volatile GitHub status remains outside of the live prose. Owner: backlog owner. |

## Procedure for the remaining external inspections

1. Observe the first actual deployment: the separation of contours is already a property
   of the environment, and the external check of the public route goes from another network in the same way
run.
2. Test the CLI transport `#180` and artifact route against the deployed environment;
   server side in the main line since 2026-08-16.
3. Obtain the human-conducted proof of OAuth/device lifecycle on the exact
expanded SHA.
4. Repeat the already proven trust and lifecycle of five immutable releases
   providers on the final CLI candidate for `Linux x86_64`; beta providers
   maintain the beta level.
5. Perform release protections, publication/operation checks, and the final `#189`.

None of these items allow push, merge, deploy, change of credentials or
publication without a separate explicit authority.
