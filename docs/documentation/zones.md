---
description: "Knowledge zones and their update rules."
last_verified: "2026-08-03"
---

# Documentation Zones

| Zone | Purpose | Update Rule |
|---|---|---|
| `docs/` | Current system design | Rewritten together with behavior |
| `specs/active/` | Current requirements | Changed before implementation or replaced by a new version |
| `specs/archive/` | Historical requirements | Not edited semantically |
| `docs/adr/` | Rationale for significant decisions | A new decision requires a new ADR |

Task statuses, checklists, and temporary compromises are not stored in `docs/`: they live in GitHub Issues and PR descriptions.
