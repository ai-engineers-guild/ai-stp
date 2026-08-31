---
description: "Dated images of inventory of separate CI/deploy trust domains and the solutions that replaced the planned barrier."
last_verified: "2026-08-16"
---

# Readiness for separating CI and deployment runners

## Purpose and scope

This is a verified snapshot of `ADR-0046` preparation, not the standard GitHub configuration
and not a promise that the external condition has not changed after the inspection date.

The deployment role that this report was awaiting did not appear and is no longer expected:
`ADR-0099` moved the deployment to the runner of the target host with an exclusive label
`ai-stp-prod`. Everything said below about `guild-ai-stp-deploy` is read as
history, and the `ADR-0046` requirement continues to be fulfilled by another mechanism.

> **Historical document.** The observations below were made before 2026-08-15 and since then
> outdated in two places. The deployment job was removed from `check.yml`: it could not
> be assigned to no runner, and the `guild-ai-stp-deploy` role no longer
> requested from nowhere. The deployment lives in a separate workflow `deploy.yml`
> and runs on the actual target host (`ADR-0099`).
> Environment `staging` in the table below is marked as missing; it exists, but
> after deleting the job, nothing uses them, and it has been removed from
> `.github/release-protection-policy.json`. The entry is saved as dated
> evidence of what the barrier was, rather than a description of the current state. Expected
roles and restrictions belong to `ADR-0046`, and the release settings —
`.github/release-protection-policy.json`. The values of secrets were not read and not
were preserved.

GitHub settings, runner registration, deployment, push and credentials in progress
the checks have not changed.

## Observed image

Read-only GitHub API and exact job logs on `2026-08-09` returned:

| Object | Observation | Conclusion |
| --- | --- | --- |
| Repository runners | two online Linux/x64 runners: `guild-ai-stp` and `guild-ai-stp-02` | two registrations do not mean two machines |
| Runner labels | both only have the custom label `guild-ai-stp` | roles `guild-ai-stp-ci` and `guild-ai-stp-deploy` are not yet activated |
| Exact successful run `31249572307` | `check` worked as `guild-ai-stp-02`, `back-python-3.12` — as `guild-ai-stp`, but both jobs reported the machine name `nddev-amsterdam`; deploy then worked as `guild-ai-stp-02` on the same machine | current CI and deploy are separated by process names, but are in the same physical trust domain |
| Environments | `total_count: 0` | `staging` and `pypi` are absent |
| Workflow token | default `read`, PR approval disabled | corresponds to minimum read boundary, but does not replace runner isolation |
| Org runner groups | API `403`, org-admin / runner-groups permission required | workflow restriction not checked |
| Branch protections and rulesets | API `403`, private plan does not support the required surface | native controls not proven |

Verified teams:

```bash
gh api repos/ai-engineers-guild/ai_stp/actions/runners
gh api repos/ai-engineers-guild/ai_stp/environments
gh api repos/ai-engineers-guild/ai_stp/actions/permissions/workflow
gh api orgs/ai-engineers-guild/actions/runner-groups
gh api repos/ai-engineers-guild/ai_stp/rulesets
gh api repos/ai-engineers-guild/ai_stp/branches/dev/protection
gh api repos/ai-engineers-guild/ai_stp/branches/main/protection
gh run view 31249572307 --log
```

Therefore, the patch with the new labels is now being closed with a rejection: the jobs will remain in
queues until individual runners are registered. Move different labels to
two current registrations are prohibited: exact logs have already proven that this is one host, and
such a transfer will return the original supply-chain defect under new names.

## Clarification of the image on 2026-08-10

The repeated read-only query modified two rows of the previous snapshot and added a third.
The CI role is activated, the deployment role is not, and the integration branch is still carrying on
the work process before strengthening.

| Object | Observation | Conclusion |
| --- | --- | --- |
| Repository runners | a third registration `guild-ai-stp-ci-omen-vm-01` appeared with a single custom label `guild-ai-stp-ci`, online, on a separate virtual machine | steps 2 and 3 of the activation sequence completed; step 4 not |
| Old common label | `guild-ai-stp` and `guild-ai-stp-02` still carry only `guild-ai-stp` | removal of the common label from step 3 was not performed |
| Deployment role | no registration carries `guild-ai-stp-deploy` | the deploy job cannot be assigned to any runner |
| Workflow on `dev` | all three jobs request `guild-ai-stp`, the deploy job has no `environment` and no source check | the integration branch runs the version before reinforcement |
| Workflow on the owner's branch | checks are requested by `guild-ai-stp-ci`, deployment — `guild-ai-stp-deploy` and `environment: staging` | after the merge, checks will run, deployment will be queued |
| Environments | still empty | `staging` not created |
| Repository secrets | three deploy names are present; `AI_STP_DEPLOY_KNOWN_HOSTS` is missing | the pinned host identity was not passed |
| Repository variables | list is empty | both the lists of allowed actors and branches are missing |

The sequence of failures after the integration of the reinforced process is known exactly and verified
by the code: first the deploy job does not get a runner; if it did get one, the check
the source would have rejected any actor because the list of allowed actors is empty
does not contain anyone; then the key preparation step would fail on the missing one
in the fixed set of known hosts. None of the failures refer to the machine
staging, so the deployed stand remains in the state of the last successful
of deployment.

From this follows the minimal list for step 4 and step 7: to register on
on a separate runner machine with a single label `guild-ai-stp-deploy`, create
environment `staging`, add a secret with a pinned set of known hosts,
obtained outside the communication channel with the host, and add two variables with lists
authorized actors and authorized source branches. Additional source verification
requires that the deployed commit be a merge commit with two parents from
to the authorized branch in the integration.

## Clarification of the image for 2026-08-12

The role of CI no longer belongs to permanent registration. According to `ADR-0080` checks
translated to the ephemeral runner scale set of the fleet `NDDev-it-com/github-actions`;
The tenant `ai-engineers-guild` owns its own GitHub App in the fleet
`guild-gha-fleet`, with its own GARM credential and organizational entity.

| Object | Observation | Conclusion |
| --- | --- | --- |
| Repository runners | all three registrations (`guild-ai-stp`, `guild-ai-stp-02`, `guild-ai-stp-ci-omen-vm-01`) are in `offline` state | no branch could get approval from checks |
| Org runners | no classic registrations; scale set is not included in this list | the presence of a scale set is checked in the fleet, not by this call |
| Org runner group `Default` | `visibility: all`, `restricted_to_workflows: false`, `allows_public_repositories: false` | repository allowed as long as it is private |
| App tenant rights | `administration:write`, `metadata:read`, `organization_self_hosted_runners:write` on the App and on the installation | the third right for the repository entity is not required and remains a deviation from minimal rights |
| Organizational entity | created and deleted: GitHub assigned a job, GARM rejected it with the `incomplete queue admission identity` cycle and did not create a runner | the queue admission layer of the overlay builds the intent only for the repository entity |
| Scale set | `nddev-linux-integration` on repository entity `ai-engineers-guild/ai_stp`, `github_scale_set_id` assigned, capacity 1, left **turned off** | GitHub accepts registration and assigns a job, but the provider rejects them (below) |
| Provider boundary | `garm-provider-incus-nddev` on the host rejects `ai_stp`: `repository is outside the configured provider boundary` | the deployed provider binary is compiled for a single repository |
| Role deployment | no registration still carries `guild-ai-stp-deploy` | deploy job still cannot be assigned |

Verified teams:

```bash
gh api /repos/ai-engineers-guild/ai_stp/actions/runners
gh api /orgs/ai-engineers-guild/actions/runners
gh api /orgs/ai-engineers-guild/actions/runner-groups
gh api /apps/guild-gha-fleet --jq .permissions
gh api /orgs/ai-engineers-guild/installations
gha-fleet reconcile-garm --tenant guild --entity-kind repository --scale-set nddev-linux-integration
```

As of the date of this snapshot, no branch had passed any checks. The transfer has been completed and
correct, but the last layer of the fleet then remained single-user: provider Incus
checks `RepoURL` against the set baked into the binary at build time, and deployed
the version only knows `NDDev-it-com/github-actions`. Failure occurs already afterwards
after GitHub assigned the job and GARM created the runner entry, therefore from the side
In the repository, it is indistinguishable from the absence of a runner: the check just sits in the queue.

Fix sent to `NDDev-it-com/github-actions#187` — provider boundary
is removed from the tenant registry. It does not take effect until the fleet owner
will rebuild and will not reinstall `garm-provider-incus-nddev` on the host. Scale set
intentionally turned off until: when turned on, it creates a failure loop every
a few seconds on a shared host.

This conclusion is captured in a snapshot on 2026-08-14 below: the fleet is servicing this job
of the repository, and the queue is no longer an observable failure.

Steps 2 and 3 of the activation sequence below relate to the permanent CI host and
replaced: the ephemeral machine does not preserve state between jobs, therefore allocation
CI host/user/filesystem is no longer a separate preparatory operation.
Steps 4–11 are retained in full and concern the role of deployment, which remained on
permanent runner.

## Clarification of the image on 2026-08-14

The fleet services the job of this repository. Provider boundary from the snapshot 2026-08-12
no longer observed: the job receives the runner, executes, and reaches
terminal verdict. The first green job on the ephemeral fleet has been received.

The observation is based on three exact runs of a workflow, not just one:

| Run | Exact commit | `check` | `back-python-3.12` |
| --- | --- | --- | --- |
| `31718481330` | `18b26cb4` (`dev`, before budget edits) | `cancelled` after 30 min 20 s | `cancelled` after 20 min 20 s |
| `31731782595` | `c7ef428f` (budget adjustments) | `failure` in 46 min 24 sec | **`success`** in 37 min 13 sec |
| `31752237134` | `3f5f3c73` (HEAD of branch) | `failure` in 49 min 22 s | **`success`** in 39 min 42 s |

Two facts follow from this table that the snapshot of 2026-08-12 could not know:

- jobs **are being executed**, not queued. Both cancellations occurred on `18b26cb4`
exactly on the boundary of the previous budgets of 30 and 20 minutes, that is, work was going on and existed
  the workflow was interrupted by the budget, not by the absence of a runner;
- budgets from `c7ef428f` are confirmed by observation, not just reasoning:
`back-python-3.12` takes 37–40 minutes, compared to the previous limit of 20 minutes
could never end.

`check` on `3f5f3c73` passed `docs-check`, `back-check`, `web-build`,
`web-static` and `web-test` worked, and failed only on `web-regress`:

| Gate inside `check` | Result on the fleet |
| --- | --- |
| `back-test` | 3000 passed, 37 skipped, coverage 93.44 % |
| `web-build` | `next build` built, 57 static pages |
| `web-static` | `tsc --noEmit` without errors |
| `web-test` | 49 files, 183 tests, all green |
| `web-regress` | 112 failed, 2 passed |

The reason for `web-regress` failure is the same and does not relate to the repository code:

```text
chrome-headless-shell: error while loading shared libraries:
libatk-1.0.so.0: cannot open shared object file: No such file or directory
```

Browser bytes in place: `web-regress` calls `ensure-chrome.sh`, which
takes the Chrome installed in the system — set by `playwright.config.ts`
`channel: "chrome"` — and downloads the browser only if it is not present. The image's **system packages** are missing.
`just web-regress` does not install them on purpose — the repository gate is not allowed to invoke it
`sudo`, — therefore they belong to the image of the ephemeral fleet machine. This is recorded
requirement for the image, not a gate defect; task — `#349`.

Verified teams:

```bash
gh run list --limit 20
gh run view 31718481330 --json headSha,jobs
gh run view 31731782595 --json headSha,jobs
gh run view 31752237134 --json headSha,jobs
gh run view --job 94620301007 --log
```

The role of the deployment was not checked by this snapshot and remains in the state of 2026-08-12:
`deploy-staging` in all three runs has the status `skipped` because the event —
`pull_request`, not push to `dev`. This is the declared behavior of the workflow, not
certificate of readiness.

## What replaced this barrier

Everything that was below is an executable runtime barrier, a sequence
an eleven-step activation and a fail-closed criterion — described a world that
no more, and therefore removed, not corrected. The barrier was waiting for two regulars
machines, `environment: staging`, `dev` branches and runner group, limited to exact
workflow. None of these objects exists.

`ADR-0046` requirement has not weakened at any point. It is being fulfilled
by three solutions, each of which is stronger than what was planned here:

| What was planned | What is in effect |
| --- | --- |
| permanent CI-host with the label `guild-ai-stp-ci` | disposable VM for a job from the fleet scale set (`ADR-0080`), not surviving its job |
| a permanent deployment host with the label `guild-ai-stp-deploy` and an SSH key | a runner on the actual target host with the single label `ai-stp-prod`, calling GitHub on outgoing 443 (`ADR-0099`); there is no deployment key anymore |
| two permanent release roles and `environment: pypi` | both jobs on `nddev-linux-standard` using different disposable workers (`ADR-0101`) |
| `environment: staging` with reviewer and branch | no tier; deployed environment is single and called `prod` (`ADR-0084`, `ADR-0086`) |
| negative probes between two live machines | contract test for all `.github/workflows/*.yml`: no other workflow has the right to name the label `ai-stp-prod` |

Three registrations, inventoried in the snapshots above — `guild-ai-stp`,
`guild-ai-stp-02` and `guild-ai-stp-ci-omen-vm-01` were deleted on 2026-08-16. For now they
they existed, any one could be lifted, and it would respond to
`runs-on: self-hosted`: the domain that this report protected lasted the longest
vulnerable precisely through them. There is only one permanent runner left in the repository,
`ai-stp-prod-kazakhstan`.

The images above are saved as dated observations. The plan in this document
no longer: job routing belongs to `docs/operations/ci-cd.md`, and the decisions —
the above-mentioned ADR.
