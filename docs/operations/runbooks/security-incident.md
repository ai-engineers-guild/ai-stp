---
description: "Runbook: security incident."
last_verified: "2026-08-03"
---

# Security incident

1. Stop distribution of the exact artifact or provider version.
2. Move the version to the `blocked` state and exclude it from automatic installation.
3. Do not publish secrets or exploitation details.
4. Identify the source commit, digest, downloads, permissions, and affected installations.
5. If necessary, revoke the compromised device or provider key.
6. Preserve the audit trail and evidence.
7. Release a corrected new version without rewriting the old one.
8. Notify affected users through a secure channel.
9. Add a regression test and update the threat model and runbook.
