---
description: "Rules for registering temporary compromises."
last_verified: "2026-08-03"
---

# Technical Debt

A record is needed if temporarily:

- mandatory verification is disabled;
- an old contract path is left;
- platform coverage is reduced;
- `not_verified` is accepted in the release path;
- migration/cleanup is postponed;
- an unsafe fallback is added.

The record includes owner, reason, cost, removal condition, deadline, and return verification. "Improve later" without an observable condition is not a record.
