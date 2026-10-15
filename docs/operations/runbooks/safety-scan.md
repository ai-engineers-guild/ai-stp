---
description: "Worker scanner ownership and handling of unavailable evidence."
last_verified: "2026-10-15"
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
