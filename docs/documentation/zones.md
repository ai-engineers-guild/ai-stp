---
description: "Knowledge zones and their update rules."
last_verified: "2026-09-20"
---

# Documentation Zones

| Zone | Purpose | Update Rule |
|---|---|---|
| `docs/` | Current system design | Rewritten together with behavior |
| `docs/archive/` | Historical plans, prototypes, checkpoints | Not edited semantically (`ADR-0194`) |
| `specs/active/` | Current requirements that match implemented code | Rewritten from code in the same change as the behavior, or replaced by a new version (`ADR-0194`) |
| `specs/archive/` | Historical requirements | Not edited semantically |
| `docs/adr/` | Rationale for significant decisions | A new decision requires a new ADR; default binding until `binding.md` lists it historical |
| `docs/engineering/implementation-canon.md` | Classification of the non-corporate tree against code | Updated when a spec, doc, or test is labelled; not a task list |

Task statuses, checklists, and temporary compromises are not stored in `docs/`: they live in GitHub Issues and PR descriptions.

Colleague corporate documents stay in their current zones and are not moved by the implementation-canon program.
