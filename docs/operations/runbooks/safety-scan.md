---
description: "Worker scanner ownership and handling of unavailable evidence."
last_verified: "2026-11-11"
---

# Safety scanning

The server worker uses the `worker-safety` target of
`deploy/docker/Dockerfile.app`. Scanner versions and installation are owned by
`scripts/safety/versions.env` and `scripts/safety/install_scanners.sh`.
`apps/platform/src/ai_stp_platform/safety` owns applicability, policy budgets,
execution and result interpretation.

Inspect the affected object's exact artifact and evidence bindings before retrying
a scan. A timeout, missing scanner or invalid input package is degraded execution,
not evidence of malicious content. Skill scanners receive the directory containing
`SKILL.md`; inapplicable checks do not run. Policy configuration owns time limits.

Use the `scripts/safety` scenario and corpus tools for affected regression checks.
Review current command arguments before any publication or rescan mutation. Never
publish fixture secrets, bypass a failed required check or relabel unavailable
evidence as success.

## Native image qualification

The `safety-runtime` workflow builds `worker-safety` on native Linux amd64 and
arm64 runners through the pinned shared CI library. Full source qualification
requires this owner. The selected runtime-image tests require their exact image,
source and architecture inputs; ordinary backend test runs report them as requiring
that separate owner.

Current image cases exercise actual Go safe/finding/incomplete results, local Go
database preparation and stale/missing refusal, the non-root worker, mandatory
Bubblewrap, filtered environment and an isolated loopback connection with a live
positive control. The named AppArmor fixture exists only in the disposable CI
runner. Proof archives contain source/image identity and the declared case results;
they grant no release permission and do not qualify untested scanner families.
