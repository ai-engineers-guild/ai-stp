---
description: "Runbook: publish recovery."
last_verified: "2026-08-03"
---

# Publication recovery

1. Find the operation ID and immutable publication plan.
2. Check whether the version was created in the registry.
3. Compare the artifact, passport, and check digests.
4. If the server record is absent, repeat only the idempotent step.
5. If the version exists with the same digest, treat the retry as idempotent.
6. If the `X.Y` number matches but the digest differs, block the conflict.
7. Do not delete the published version; if there is risk, set its state to `blocked`.
8. Build a new plan for further actions.
