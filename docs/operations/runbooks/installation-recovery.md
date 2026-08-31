---
description: "Runbook: installation recovery."
last_verified: "2026-08-03"
---

# Installation recovery

1. Stop new changes to the target.
2. Read the operation log and provider result.
3. Distinguish among applied-but-unverified, partial, and failed states.
4. Check the current target digest and backup reference.
5. Do not blindly repeat the application.
6. Verify the provider state.
7. If the new target is intact, repeat result verification.
8. Otherwise, build a plan to restore the exact backup.
9. Verify the restored state and active pointer.
10. Record residual uncertainty.
