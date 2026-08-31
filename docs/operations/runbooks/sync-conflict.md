---
description: "Runbook: sync conflict."
last_verified: "2026-08-03"
---

# Sync conflict

1. Do not overwrite the local or cloud head.
2. Obtain the common ancestor and affected fields.
3. Verify device and account authority.
4. Automatically merge independent fields.
5. Show the user the conflicting values and their provenance.
6. Create a merged revision with two parents after resolution.
7. Retry the submission using the idempotency key.
8. Ensure that the target and installation state have not changed.

A revoked device may read local state but does not submit changes.
